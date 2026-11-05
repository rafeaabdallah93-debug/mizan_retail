"""Branches for a single company: each branch is one Warehouse plus one POS Profile (till).

The branch Warehouse sits under the company's root warehouse group, so stock posted at one
branch never touches another. The POS Profile is named like the Warehouse ("<branch> - <abbr>")
so the same branch name can exist in different companies.
"""

import frappe
from frappe import _

CASH_MODE_TYPE = "Cash"
SAVEPOINT = "mizan_create_branch"


@frappe.whitelist()
def create_branch(company: str, branch_name: str) -> dict:
	"""Create the Warehouse and POS Profile for `branch_name` in `company`.

	Returns {"warehouse": <Warehouse name>, "pos_profile": <POS Profile name>}.
	Everything is validated before anything is written; on any error nothing is left behind.
	"""
	branch_name = (branch_name or "").strip()
	if not branch_name:
		frappe.throw(_("Branch name is required."))
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(company))

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

	frappe.db.savepoint(SAVEPOINT)
	try:
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
				"selling_price_list": settings["price_list"],
				"write_off_account": settings["write_off_account"],
				"write_off_cost_center": settings["cost_center"],
				"cost_center": settings["cost_center"],
				"update_stock": 1,
				"payments": [{"mode_of_payment": settings["cash_mode"], "default": 1}],
			}
		).insert()
	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		raise

	return {"warehouse": warehouse.name, "pos_profile": pos_profile.name}


@frappe.whitelist()
def delete_branch(company: str, branch_name: str) -> None:
	"""Delete the branch's POS Profile(s), then its Warehouse. Refused while the Warehouse has
	stock or any stock ledger entries."""
	branch_name = (branch_name or "").strip()
	warehouse = _branch_warehouse(company, branch_name)
	if not warehouse:
		frappe.throw(
			_("Branch {0} does not exist for company {1}.").format(frappe.bold(branch_name), company)
		)

	stocked = frappe.get_all(
		"Bin", filters={"warehouse": warehouse, "actual_qty": ("!=", 0)}, pluck="item_code", limit=1
	)
	if stocked:
		frappe.throw(
			_("Cannot delete branch {0}: its warehouse still holds stock of item {1}.").format(
				frappe.bold(branch_name), stocked[0]
			),
			title=_("Branch Has Stock"),
		)
	if frappe.db.exists("Stock Ledger Entry", {"warehouse": warehouse}):
		frappe.throw(
			_("Cannot delete branch {0}: its warehouse has stock transactions.").format(
				frappe.bold(branch_name)
			),
			title=_("Branch Has Stock"),
		)

	for profile in frappe.get_all("POS Profile", filters={"warehouse": warehouse}, pluck="name"):
		frappe.delete_doc("POS Profile", profile)
	frappe.delete_doc("Warehouse", warehouse)


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
		"price_list": _selling_price_list(values.default_currency),
	}


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


def _selling_price_list(currency: str) -> str:
	"""The default selling Price List if it is in `currency`, else another enabled selling list in
	it, else a new "Standard Selling <currency>" list."""
	default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if default and frappe.db.get_value("Price List", default, ["currency", "enabled", "selling"]) == (
		currency,
		1,
		1,
	):
		return default

	existing = frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1, "currency": currency}, order_by="creation asc"
	)
	if existing:
		return existing

	return (
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": f"Standard Selling {currency}",
				"currency": currency,
				"selling": 1,
				"enabled": 1,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
