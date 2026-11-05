import json
import os

import frappe
from frappe.tests import IntegrationTestCase
from mizan_core.tests.translation_check import missing_arabic_translations


class TestArabicTranslations(IntegrationTestCase):
	def test_every_string_has_arabic(self):
		self.assertTrue(os.path.exists(frappe.get_app_path("mizan_retail", "locale", "ar.po")))
		self.assertEqual(missing_arabic_translations("mizan_retail"), [])


class TestAddBranchIsReachable(IntegrationTestCase):
	"""The Add Branch page is linked from the desk: a Mizan Retail workspace with a shortcut, a
	sidebar entry, and a rail icon mounted on ERPNext's rail."""

	def test_workspace_has_add_branch_shortcut(self):
		workspace = frappe.get_doc("Workspace", "Mizan Retail")
		self.assertTrue(workspace.public)
		self.assertFalse(workspace.is_hidden)
		self.assertIn(("Page", "add-branch"), [(s.type, s.link_to) for s in workspace.shortcuts])
		blocks = [block["data"].get("shortcut_name") for block in json.loads(workspace.content)]
		self.assertIn("Add Branch", blocks)

	def test_sidebar_and_rail_link_to_add_branch(self):
		sidebar = frappe.get_doc("Sidebar", "Mizan Retail")
		self.assertIn(("Page", "add-branch"), [(i.link_type, i.link_to) for i in sidebar.items])
		dock = frappe.get_doc("Dock", {"app": "mizan_retail", "standard": 1})
		self.assertEqual(dock.mount_on, "erpnext")
		self.assertIn(("Sidebar", "Mizan Retail"), [(i.link_type, i.link_to) for i in dock.items])
