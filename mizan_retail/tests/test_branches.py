import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, now_datetime, nowdate
from mizan_core.setup.egypt_defaults import apply_egypt_defaults

from mizan_retail.branches import create_branch, delete_branch

TEST_COMPANY = "Mizan Retail Test Co"
TEST_ABBR = "MRTC"
TEST_ITEM = "MRT-BRANCH-ITEM"
TEST_CUSTOMER = "MRT Walk-in Customer"
ARABIC_BRANCH = "فرع المعادي"


def _unique(label: str) -> str:
	# Stock-carrying branches cannot be deleted, so each run uses fresh names.
	return f"{label} {frappe.generate_hash(length=6)}"


def _bin_qty(warehouse: str, item_code: str = TEST_ITEM) -> float:
	return flt(frappe.db.get_value("Bin", {"warehouse": warehouse, "item_code": item_code}, "actual_qty"))


def _receive(warehouse: str, qty: float, rate: float = 50) -> None:
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": TEST_COMPANY,
			"items": [{"item_code": TEST_ITEM, "qty": qty, "t_warehouse": warehouse, "basic_rate": rate}],
		}
	)
	entry.insert()
	entry.submit()


def _vat_account() -> str:
	return frappe.db.get_value("Account", {"company": TEST_COMPANY, "account_number": "2200", "is_group": 0})


def _open_till(pos_profile: str) -> None:
	"""Open the till for today, as the cashier does before the first sale."""
	profile = frappe.get_doc("POS Profile", pos_profile)
	entry = frappe.get_doc(
		{
			"doctype": "POS Opening Entry",
			"period_start_date": now_datetime(),
			"posting_date": nowdate(),
			"company": profile.company,
			"pos_profile": pos_profile,
			"user": frappe.session.user,
			"balance_details": [
				{"mode_of_payment": row.mode_of_payment, "opening_amount": 0} for row in profile.payments
			],
		}
	)
	entry.insert()
	entry.submit()


def _till_sale(pos_profile: str, qty: float, rate: float):
	"""A sale as the POS screen submits it: customer, till and items only."""
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": TEST_COMPANY,
			"customer": TEST_CUSTOMER,
			"is_pos": 1,
			"is_created_using_pos": 1,
			"pos_profile": pos_profile,
			"items": [{"item_code": TEST_ITEM, "qty": qty, "rate": rate}],
		}
	)
	invoice.set_missing_values()
	invoice.calculate_taxes_and_totals()
	for row in invoice.payments:
		row.amount = (invoice.rounded_total or invoice.grand_total) if row.default else 0
	invoice.insert()
	invoice.submit()
	return invoice


def _leaf(doctype: str) -> str:
	return frappe.db.get_value(doctype, {"is_group": 0}, order_by="lft asc")


class TestBranches(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		apply_egypt_defaults(TEST_COMPANY, abbr=TEST_ABBR)
		if not frappe.db.exists("Item", TEST_ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": TEST_ITEM,
					"item_name": "Mizan branch test item",
					"item_group": _leaf("Item Group"),
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			).insert()
		if not frappe.db.exists("Customer", TEST_CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": TEST_CUSTOMER,
					"customer_group": _leaf("Customer Group"),
					"territory": _leaf("Territory"),
				}
			).insert()

	def test_create_branch_makes_warehouse_and_pos_profile(self):
		branch = _unique("Zamalek")
		result = create_branch(TEST_COMPANY, branch)

		warehouse = frappe.get_doc("Warehouse", result["warehouse"])
		self.assertEqual(warehouse.warehouse_name, branch)
		self.assertEqual(warehouse.company, TEST_COMPANY)
		self.assertFalse(warehouse.is_group)
		root = frappe.db.get_value("Warehouse", warehouse.parent_warehouse, ["company", "is_group"], as_dict=True)
		self.assertEqual(root.company, TEST_COMPANY)
		self.assertTrue(root.is_group)

		profile = frappe.get_doc("POS Profile", result["pos_profile"])
		self.assertEqual(profile.company, TEST_COMPANY)
		self.assertEqual(profile.warehouse, result["warehouse"])
		self.assertEqual(profile.currency, "EGP")
		self.assertTrue(profile.update_stock)
		self.assertEqual(frappe.db.get_value("Price List", profile.selling_price_list, "currency"), "EGP")
		self.assertEqual(len(profile.payments), 1)
		self.assertEqual(frappe.db.get_value("Mode of Payment", profile.payments[0].mode_of_payment, "type"), "Cash")
		self.assertTrue(profile.payments[0].default)
		self.assertEqual(frappe.db.get_value("Account", profile.write_off_account, "company"), TEST_COMPANY)
		self.assertEqual(frappe.db.get_value("Cost Center", profile.write_off_cost_center, "company"), TEST_COMPANY)

	def test_duplicate_branch_name_raises(self):
		branch = _unique("Heliopolis")
		create_branch(TEST_COMPANY, branch)
		warehouses = frappe.db.count("Warehouse", {"company": TEST_COMPANY})
		profiles = frappe.db.count("POS Profile", {"company": TEST_COMPANY})

		with self.assertRaises(frappe.ValidationError):
			create_branch(TEST_COMPANY, branch)

		self.assertEqual(frappe.db.count("Warehouse", {"company": TEST_COMPANY}), warehouses)
		self.assertEqual(frappe.db.count("POS Profile", {"company": TEST_COMPANY}), profiles)

	def test_whitespace_variant_is_duplicate(self):
		suffix = frappe.generate_hash(length=6)
		result = create_branch(TEST_COMPANY, f"Maadi Branch {suffix}")
		self.assertEqual(frappe.db.get_value("Warehouse", result["warehouse"], "warehouse_name"), f"Maadi Branch {suffix}")

		with self.assertRaises(frappe.ValidationError):
			create_branch(TEST_COMPANY, f"  Maadi  Branch   {suffix} ")

	def test_name_with_company_suffix_refused(self):
		branch = _unique("Agouza")
		with self.assertRaises(frappe.ValidationError):
			create_branch(TEST_COMPANY, f"{branch} - {TEST_ABBR}")
		self.assertFalse(frappe.db.exists("Warehouse", {"warehouse_name": ("like", f"{branch}%")}))

	def test_unsuitable_standard_price_list_refused_cleanly(self):
		# Only a disabled "Standard Selling EGP" exists: a clear ValidationError, no partial records.
		enabled = frappe.get_all(
			"Price List", filters={"currency": "EGP", "selling": 1, "enabled": 1}, pluck="name"
		)
		for name in enabled:
			frappe.db.set_value("Price List", name, "enabled", 0)
			self.addCleanup(frappe.db.set_value, "Price List", name, "enabled", 1)
		if not frappe.db.exists("Price List", "Standard Selling EGP"):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": "Standard Selling EGP",
					"currency": "EGP",
					"selling": 1,
					"enabled": 0,
				}
			).insert()
		warehouses = frappe.db.count("Warehouse", {"company": TEST_COMPANY})

		with self.assertRaises(frappe.ValidationError):
			create_branch(TEST_COMPANY, _unique("Garden City"))

		self.assertEqual(frappe.db.count("Warehouse", {"company": TEST_COMPANY}), warehouses)

	def test_arabic_branch_name_saves(self):
		if frappe.db.exists("Warehouse", {"warehouse_name": ARABIC_BRANCH, "company": TEST_COMPANY}):
			delete_branch(TEST_COMPANY, ARABIC_BRANCH)  # left behind by an earlier committed run

		result = create_branch(TEST_COMPANY, ARABIC_BRANCH)

		self.assertEqual(frappe.db.get_value("Warehouse", result["warehouse"], "warehouse_name"), ARABIC_BRANCH)
		self.assertIn(ARABIC_BRANCH, result["warehouse"])
		self.assertIn(ARABIC_BRANCH, result["pos_profile"])
		self.assertEqual(frappe.db.get_value("POS Profile", result["pos_profile"], "warehouse"), result["warehouse"])

		found = frappe.get_all("Warehouse", filters={"warehouse_name": ["like", "%المعادي%"]}, pluck="name")
		self.assertIn(result["warehouse"], found)

		delete_branch(TEST_COMPANY, ARABIC_BRANCH)
		self.assertFalse(frappe.db.exists("Warehouse", result["warehouse"]))
		self.assertFalse(frappe.db.exists("POS Profile", result["pos_profile"]))

	def test_delete_branch_with_stock_refused(self):
		branch = _unique("Nasr City")
		result = create_branch(TEST_COMPANY, branch)
		_receive(result["warehouse"], 5)

		with self.assertRaises(frappe.ValidationError):
			delete_branch(TEST_COMPANY, branch)

		self.assertTrue(frappe.db.exists("Warehouse", result["warehouse"]))
		self.assertTrue(frappe.db.exists("POS Profile", result["pos_profile"]))

	def test_delete_branch_with_open_request_refused(self):
		# No stock and no ledger entries, but a submitted Material Request raises indented_qty
		# (and projected_qty) in the branch Bin, which ERPNext's Warehouse.on_trash also refuses.
		branch = _unique("Mohandessin")
		result = create_branch(TEST_COMPANY, branch)
		request = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": TEST_COMPANY,
				"schedule_date": nowdate(),
				"items": [
					{
						"item_code": TEST_ITEM,
						"qty": 3,
						"uom": "Nos",
						"warehouse": result["warehouse"],
						"schedule_date": nowdate(),
					}
				],
			}
		)
		request.insert()
		request.submit()
		self.assertEqual(_bin_qty(result["warehouse"]), 0)
		self.assertEqual(
			flt(frappe.db.get_value("Bin", {"warehouse": result["warehouse"], "item_code": TEST_ITEM}, "indented_qty")),
			3,
		)
		self.assertFalse(frappe.db.exists("Stock Ledger Entry", {"warehouse": result["warehouse"]}))

		with self.assertRaises(frappe.ValidationError):
			delete_branch(TEST_COMPANY, branch)

		self.assertTrue(frappe.db.exists("Warehouse", result["warehouse"]))
		self.assertTrue(frappe.db.exists("POS Profile", result["pos_profile"]))

	def test_till_sale_charges_vat_and_reduces_only_that_branch_stock(self):
		# The till path: POS Settings' invoice type is "Sales Invoice", so the POS screen makes a
		# Sales Invoice with is_created_using_pos=1 under an open POS Opening Entry. Only the
		# customer, the till and the items are given; warehouse, taxes and payments come from the
		# POS Profile through ERPNext's set_pos_fields. Shelf prices include VAT: 114 = 100 + 14%.
		branch_a = create_branch(TEST_COMPANY, _unique("Dokki"))
		branch_b = create_branch(TEST_COMPANY, _unique("Giza"))
		_receive(branch_a["warehouse"], 10)
		_receive(branch_b["warehouse"], 10)
		_open_till(branch_a["pos_profile"])

		invoice = _till_sale(branch_a["pos_profile"], qty=1, rate=114)

		self.assertEqual(invoice.items[0].warehouse, branch_a["warehouse"])
		self.assertEqual(_bin_qty(branch_a["warehouse"]), 9)
		self.assertEqual(_bin_qty(branch_b["warehouse"]), 10)

		vat_account = _vat_account()
		self.assertTrue(invoice.taxes, "a till sale must carry the company's VAT")
		self.assertEqual([row.account_head for row in invoice.taxes], [vat_account])
		self.assertEqual(flt(invoice.grand_total), 114)
		self.assertEqual(flt(invoice.net_total), 100)
		self.assertEqual(flt(invoice.total_taxes_and_charges), 14)

		credits = {}
		for entry in frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Sales Invoice", "voucher_no": invoice.name, "is_cancelled": 0},
			fields=["account", "credit"],
		):
			credits[entry.account] = credits.get(entry.account, 0) + flt(entry.credit)
		self.assertEqual(credits.get(invoice.items[0].income_account), 100)
		self.assertEqual(credits.get(vat_account), 14)

	def test_branch_till_uses_company_default_sales_tax(self):
		result = create_branch(TEST_COMPANY, _unique("Sheikh Zayed"))

		template = frappe.db.get_value("POS Profile", result["pos_profile"], "taxes_and_charges")
		self.assertTrue(template)
		self.assertEqual(
			frappe.db.get_value(
				"Sales Taxes and Charges Template", template, ["company", "is_default", "disabled"]
			),
			(TEST_COMPANY, 1, 0),
		)

	def test_company_without_default_sales_tax_refused_cleanly(self):
		for name in frappe.get_all(
			"Sales Taxes and Charges Template",
			filters={"company": TEST_COMPANY, "is_default": 1},
			pluck="name",
		):
			frappe.db.set_value("Sales Taxes and Charges Template", name, "is_default", 0)
			self.addCleanup(frappe.db.set_value, "Sales Taxes and Charges Template", name, "is_default", 1)
		warehouses = frappe.db.count("Warehouse", {"company": TEST_COMPANY})
		profiles = frappe.db.count("POS Profile", {"company": TEST_COMPANY})

		with self.assertRaises(frappe.ValidationError):
			create_branch(TEST_COMPANY, _unique("Obour"))

		self.assertEqual(frappe.db.count("Warehouse", {"company": TEST_COMPANY}), warehouses)
		self.assertEqual(frappe.db.count("POS Profile", {"company": TEST_COMPANY}), profiles)

	def test_patch_backfills_till_tax_template(self):
		from mizan_retail.patches.v1_0.set_pos_profile_sales_taxes import execute

		result = create_branch(TEST_COMPANY, _unique("Haram"))
		expected = frappe.db.get_value("POS Profile", result["pos_profile"], "taxes_and_charges")
		frappe.db.set_value("POS Profile", result["pos_profile"], "taxes_and_charges", None)

		execute()

		self.assertEqual(
			frappe.db.get_value("POS Profile", result["pos_profile"], "taxes_and_charges"), expected
		)

	def test_transfer_moves_stock_between_branches(self):
		branch_a = create_branch(TEST_COMPANY, _unique("Maadi"))
		branch_b = create_branch(TEST_COMPANY, _unique("Shubra"))
		_receive(branch_a["warehouse"], 10)

		transfer = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"company": TEST_COMPANY,
				"items": [
					{
						"item_code": TEST_ITEM,
						"qty": 4,
						"s_warehouse": branch_a["warehouse"],
						"t_warehouse": branch_b["warehouse"],
					}
				],
			}
		)
		transfer.insert()
		transfer.submit()

		self.assertEqual(_bin_qty(branch_a["warehouse"]), 6)
		self.assertEqual(_bin_qty(branch_b["warehouse"]), 4)
