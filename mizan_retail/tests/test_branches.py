import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, nowdate
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


def _ensure_site_fixtures() -> None:
	"""A bare CI site has never run the setup wizard: no Cash mode, UOMs, stock entry types,
	groups, fiscal year or System Settings language (mandatory when System Settings is saved).
	Fill in what is missing, as the setup wizard would."""
	if not frappe.db.get_single_value("System Settings", "language"):
		frappe.db.set_single_value("System Settings", "language", "en")

	if not frappe.db.exists("Stock Entry Type", "Material Receipt"):
		from erpnext.setup.setup_wizard.operations.install_fixtures import install

		install(country="Egypt")

	today = getdate(nowdate())
	if not frappe.db.exists(
		"Fiscal Year", {"year_start_date": ("<=", today), "year_end_date": (">=", today), "disabled": 0}
	):
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": str(today.year),
				"year_start_date": f"{today.year}-01-01",
				"year_end_date": f"{today.year}-12-31",
			}
		).insert()


def _leaf(doctype: str) -> str:
	return frappe.db.get_value(doctype, {"is_group": 0}, order_by="lft asc")


class TestBranches(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_site_fixtures()
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

	def test_arabic_branch_name_saves(self):
		if frappe.db.exists("Warehouse", {"warehouse_name": ARABIC_BRANCH, "company": TEST_COMPANY}):
			delete_branch(TEST_COMPANY, ARABIC_BRANCH)  # left behind by an earlier committed run

		result = create_branch(TEST_COMPANY, ARABIC_BRANCH)

		self.assertEqual(frappe.db.get_value("Warehouse", result["warehouse"], "warehouse_name"), ARABIC_BRANCH)
		self.assertIn(ARABIC_BRANCH, result["warehouse"])
		self.assertIn(ARABIC_BRANCH, result["pos_profile"])
		self.assertEqual(frappe.db.get_value("POS Profile", result["pos_profile"], "warehouse"), result["warehouse"])

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

	def test_sale_reduces_only_that_branch_stock(self):
		branch_a = create_branch(TEST_COMPANY, _unique("Dokki"))
		branch_b = create_branch(TEST_COMPANY, _unique("Giza"))
		_receive(branch_a["warehouse"], 10)
		_receive(branch_b["warehouse"], 10)

		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": TEST_COMPANY,
				"customer": TEST_CUSTOMER,
				"is_pos": 1,
				"pos_profile": branch_a["pos_profile"],
				"update_stock": 1,
				"items": [{"item_code": TEST_ITEM, "qty": 3, "rate": 100}],
			}
		)
		invoice.set_missing_values()
		invoice.calculate_taxes_and_totals()
		self.assertEqual(invoice.items[0].warehouse, branch_a["warehouse"])
		invoice.set("payments", [])
		invoice.append(
			"payments",
			{
				"mode_of_payment": frappe.get_doc("POS Profile", branch_a["pos_profile"]).payments[0].mode_of_payment,
				"amount": invoice.rounded_total or invoice.grand_total,
				"default": 1,
			},
		)
		invoice.insert()
		invoice.submit()

		self.assertEqual(_bin_qty(branch_a["warehouse"]), 7)
		self.assertEqual(_bin_qty(branch_b["warehouse"]), 10)

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
