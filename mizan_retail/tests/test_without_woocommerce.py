import os
import re

import frappe
from frappe.tests import IntegrationTestCase
from mizan_core.setup.egypt_defaults import apply_egypt_defaults

from mizan_retail.branches import create_branch
from mizan_retail.tests.test_branches import TEST_ABBR, TEST_COMPANY, _unique


class TestWithoutWooCommerce(IntegrationTestCase):
	"""Guard: the WooCommerce connector is optional. A site without it must work normally."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		apply_egypt_defaults(TEST_COMPANY, abbr=TEST_ABBR)

	def test_apps_work_without_woocommerce(self):
		# Never passes vacuously: with the connector absent it exercises create_branch;
		# with it present it falls back to the static import check.
		if "woocommerce_fusion" in frappe.get_installed_apps():
			self._assert_no_connector_imports()
			return
		result = create_branch(TEST_COMPANY, _unique("No Shop"))
		self.assertTrue(frappe.db.exists("Warehouse", result["warehouse"]))
		self.assertTrue(frappe.db.exists("POS Profile", result["pos_profile"]))

	def test_mizan_apps_do_not_import_woocommerce(self):
		self._assert_no_connector_imports()

	def _assert_no_connector_imports(self):
		pattern = re.compile(r"^\s*(import|from)\s+woocommerce_fusion\b", re.MULTILINE)
		checked = 0
		offenders = []
		for app in ("mizan_core", "mizan_retail"):
			for root, _dirs, files in os.walk(frappe.get_app_path(app)):
				for name in files:
					if not name.endswith(".py"):
						continue
					path = os.path.join(root, name)
					if os.path.basename(root) == "tests" or name.startswith("test_"):
						continue
					checked += 1
					with open(path, encoding="utf-8") as f:
						if pattern.search(f.read()):
							offenders.append(path)
		self.assertGreater(checked, 0)
		self.assertEqual(offenders, [], "Mizan apps must not import woocommerce_fusion")
