"""Acceptance contract: dev-ortam checkpoint 1 and owner module decision."""

import frappe
from frappe.tests import IntegrationTestCase


class TestInstallation(IntegrationTestCase):
	def test_application_is_installed(self):
		self.assertIn("platform_core", frappe.get_installed_apps())

	def test_module_definitions(self):
		modules = set(frappe.get_all("Module Def", filters={"app_name": "platform_core"}, pluck="name"))
		self.assertEqual(
			modules, {"Identity", "Shell", "AI", "Model Gateway", "Mobile", "Access", "Reseller"}
		)
