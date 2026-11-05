"""Tills created before create_branch set a tax template charge no VAT: fill in the company's
default sales tax template on every POS Profile that has none. Profiles of companies without
a default template are left as they are."""

import frappe

from mizan_retail.branches import default_sales_tax_template


def execute():
	for profile in frappe.get_all(
		"POS Profile",
		filters={"taxes_and_charges": ("is", "not set")},
		fields=["name", "company"],
	):
		template = default_sales_tax_template(profile.company)
		if template:
			frappe.db.set_value("POS Profile", profile.name, "taxes_and_charges", template)
