import frappe
from frappe.tests import IntegrationTestCase
from mizan_core.setup.egypt_defaults import apply_egypt_defaults

from mizan_retail.branches import create_branch
from mizan_retail.tests.test_branches import TEST_ABBR, TEST_COMPANY, _ensure_site_fixtures, _unique


class TestWithoutWooCommerce(IntegrationTestCase):
	"""Guard: the WooCommerce connector is optional. A site without it must work normally."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_site_fixtures()
		apply_egypt_defaults(TEST_COMPANY, abbr=TEST_ABBR)

	def test_apps_work_without_woocommerce(self):
		# Run this on a site that does not have the connector (dev.localhost).
		if "woocommerce_fusion" in frappe.get_installed_apps():
			self.skipTest("woocommerce_fusion is installed on this site; guard applies to sites without it")
		self.assertNotIn("woocommerce_fusion", frappe.get_installed_apps())

		result = create_branch(TEST_COMPANY, _unique("No Shop"))
		self.assertTrue(frappe.db.exists("Warehouse", result["warehouse"]))
		self.assertTrue(frappe.db.exists("POS Profile", result["pos_profile"]))
