"""Branches for a single company: each branch is one Warehouse plus one POS Profile (till).

The branch Warehouse sits under the company's root warehouse group, so stock posted at one
branch never touches another. The POS Profile is named like the Warehouse ("<branch> - <abbr>")
so the same branch name can exist in different companies.
"""

import frappe
from frappe import _

CASH_MODE_TYPE = "Cash"
CREATE_SAVEPOINT = "mizan_create_branch"
DELETE_SAVEPOINT = "mizan_delete_branch"

# Every Bin quantity ERPNext's Warehouse.on_trash refuses on (warehouse.py get_bin_with_quantity).
BIN_QTY_FIELDS = (
	"actual_qty",
	"reserved_qty",
	"ordered_qty",
	"indented_qty",
	"projected_qty",
	"planned_qty",
)


@frappe.whitelist()
def create_branch(company: str, branch_name: str) -> dict:
	"""Create the Warehouse and POS Profile for `branch_name` in `company`.

	Returns {"warehouse": <Warehouse name>, "pos_profile": <POS Profile name>}.
	Everything is validated before anything is written; on any error nothing is left behind.
	"""
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(company))
	branch_name = _normalise_name(company, branch_name)

	frappe.has_permission("Warehouse", "create", throw=True)
	frappe.has_permission("POS Profile", "create", throw=True)

	name = _branch_doc_name(company, branch_name)
	if _branch_warehouse(company, branch_name) or frappe.db.exists("Warehouse", name):
		frappe.throw(
			_("Branch {0} already exists for company {1}.").format(frappe.bold(branch_name), company),
			title=_("Duplicate Branch"),
		)
	if frappe.db.exists("POS Profile", name):
		frappe.throw(
			_("A POS Profile named {0} already exists.").format(frappe.bold(name)),
			title=_("Duplicate Branch"),
		)

	settings = _pos_settings(company)

	frappe.db.savepoint(CREATE_SAVEPOINT)
	try:
		price_list = _selling_price_list(settings["currency"])
		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": branch_name,
				"company": company,
				"parent_warehouse": settings["parent_warehouse"],
				"is_group": 0,
			}
		).insert()

		pos_profile = frappe.get_doc(
			{
				"doctype": "POS Profile",
				"name": name,
				"company": company,
				"warehouse": warehouse.name,
				"currency": settings["currency"],
				"selling_price_list": price_list,
				"write_off_account": settings["write_off_account"],
				"write_off_cost_center": settings["cost_center"],
				"cost_center": settings["cost_center"],
				"taxes_and_charges": settings["taxes_and_charges"],
				"update_stock": 1,
				"payments": [{"mode_of_payment": settings["cash_mode"], "default": 1}],
			}
		).insert()
	except Exception:
		frappe.db.rollback(save_point=CREATE_SAVEPOINT)
		raise

	return {"warehouse": warehouse.name, "pos_profile": pos_profile.name}


@frappe.whitelist()
def delete_branch(company: str, branch_name: str) -> None:
	"""Delete the branch's POS Profile(s), then its Warehouse.

	Refused while the Warehouse has any non-zero stock quantity (actual, reserved, ordered,
	requested, projected or planned) or any stock ledger entries. Both deletes run in one savepoint,
	so if ERPNext refuses the Warehouse (e.g. linked submitted documents) the till is kept too.
	"""
	frappe.has_permission("Warehouse", "delete", throw=True)
	frappe.has_permission("POS Profile", "delete", throw=True)

	branch_name = " ".join((branch_name or "").split())
	warehouse = _branch_warehouse(company, branch_name)
	if not warehouse:
		frappe.throw(
			_("Branch {0} does not exist for company {1}.").format(frappe.bold(branch_name), company)
		)

	for row in frappe.get_all(
		"Bin", filters={"warehouse": warehouse}, fields=["item_code", *BIN_QTY_FIELDS]
	):
		if any(row.get(field) for field in BIN_QTY_FIELDS):
			frappe.throw(
				_(
					"Cannot delete branch {0}: its warehouse still has stock, orders, requests or reservations for item {1}."
				).format(frappe.bold(branch_name), row.item_code),
				title=_("Branch Has Stock"),
			)
	if frappe.db.exists("Stock Ledger Entry", {"warehouse": warehouse}):
		frappe.throw(
			_("Cannot delete branch {0}: its warehouse has stock transactions.").format(
				frappe.bold(branch_name)
			),
			title=_("Branch Has Stock"),
		)

	frappe.db.savepoint(DELETE_SAVEPOINT)
	try:
		for profile in frappe.get_all("POS Profile", filters={"warehouse": warehouse}, pluck="name"):
			frappe.delete_doc("POS Profile", profile)
		frappe.delete_doc("Warehouse", warehouse)
	except Exception:
		frappe.db.rollback(save_point=DELETE_SAVEPOINT)
		raise


def _normalise_name(company: str, branch_name: str) -> str:
	"""Trim and collapse whitespace; refuse empty names and names already carrying the suffix."""
	branch_name = " ".join((branch_name or "").split())
	if not branch_name:
		frappe.throw(_("Branch name is required."))
	suffix = " - " + frappe.get_cached_value("Company", company, "abbr")
	if branch_name.endswith(suffix):
		frappe.throw(
			_("Enter the branch name without the company abbreviation {0}.").format(frappe.bold(suffix.strip(" -")))
		)
	return branch_name


def _branch_doc_name(company: str, branch_name: str) -> str:
	abbr = frappe.get_cached_value("Company", company, "abbr")
	return f"{branch_name} - {abbr}"


def _branch_warehouse(company: str, branch_name: str) -> str | None:
	return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": branch_name, "is_group": 0})


def _pos_settings(company: str) -> dict:
	"""Collect the company values a branch till needs; throw a clear message when one is missing."""
	values = frappe.get_cached_value(
		"Company", company, ["default_currency", "write_off_account", "cost_center"], as_dict=True
	)
	missing = [
		label
		for label, value in (
			(_("Default Currency"), values.default_currency),
			(_("Write Off Account"), values.write_off_account),
			(_("Default Cost Center"), values.cost_center),
		)
		if not value
	]
	if missing:
		frappe.throw(_("Set {0} on company {1} before adding a branch.").format(", ".join(missing), company))

	return {
		"currency": values.default_currency,
		"write_off_account": values.write_off_account,
		"cost_center": values.cost_center,
		"parent_warehouse": _root_warehouse(company),
		"cash_mode": _cash_mode_of_payment(company),
		"taxes_and_charges": _required_sales_tax_template(company),
	}


def default_sales_tax_template(company: str) -> str | None:
	"""The company's default, enabled Sales Taxes and Charges Template (mizan_core's "Egypt VAT")."""
	return frappe.db.get_value(
		"Sales Taxes and Charges Template",
		{"company": company, "is_default": 1, "disabled": 0},
		order_by="creation asc",
	)


def _required_sales_tax_template(company: str) -> str:
	"""A till must charge VAT: ERPNext's POS copies the profile's taxes_and_charges onto every
	sale (set_pos_fields), and adds no tax at all when it is empty."""
	template = default_sales_tax_template(company)
	if not template:
		frappe.throw(
			_(
				"Company {0} has no default sales tax template, so the till could not charge VAT. Mark the company's Sales Taxes and Charges Template (for example Egypt VAT) as default, then add the branch again."
			).format(company),
			title=_("Missing Tax Template"),
		)
	return template


def _root_warehouse(company: str) -> str:
	root = frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 1, "parent_warehouse": ("is", "not set")},
		order_by="lft asc",
	)
	if not root:
		frappe.throw(_("Company {0} has no warehouse group to add the branch under.").format(company))
	return root


def _cash_mode_of_payment(company: str) -> str:
	"""An enabled Cash Mode of Payment that already has an account for this company."""
	for mode in frappe.get_all("Mode of Payment", filters={"type": CASH_MODE_TYPE, "enabled": 1}, pluck="name"):
		if frappe.db.get_value("Mode of Payment Account", {"parent": mode, "company": company}, "default_account"):
			return mode
	frappe.throw(
		_("No Cash Mode of Payment has an account for company {0}. Set one in Mode of Payment.").format(
			company
		),
		title=_("Missing Account"),
	)


def _price_list_suits(name: str, currency: str) -> bool:
	values = frappe.db.get_value("Price List", name, ["currency", "enabled", "selling"], as_dict=True)
	return bool(values) and values.currency == currency and values.enabled and values.selling


def _selling_price_list(currency: str) -> str:
	"""The default selling Price List if it suits (enabled, selling, `currency`), else another
	suitable list, else a new "Standard Selling <currency>" list. Must run inside the caller's
	savepoint so a created list is rolled back with the branch."""
	default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if default and _price_list_suits(default, currency):
		return default

	existing = frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1, "currency": currency}, order_by="creation asc"
	)
	if existing:
		return existing

	name = f"Standard Selling {currency}"
	if frappe.db.exists("Price List", name):
		# Not suitable, or the lookup above would have found it.
		frappe.throw(
			_(
				"Price List {0} exists but is not an enabled selling price list in {1}. Enable it for selling in {1}, or create one, then add the branch again."
			).format(frappe.bold(name), currency),
			title=_("Missing Price List"),
		)

	return (
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": name,
				"currency": currency,
				"selling": 1,
				"enabled": 1,
			}
		)
		.insert()
		.name
	)
