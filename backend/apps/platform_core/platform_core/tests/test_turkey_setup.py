"""G-41: the Türkiye defaults survive the setup wizard and a second run changes nothing.

The test runs on a separate test site through `bin/test`.
"""

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.config import turkey_setup

EXPECTED = {
	"country": "Türkiye",
	"language": "tr",
	"time_zone": "Europe/Istanbul",
	"currency": "TRY",
	"number_format": "#.###,##",
	"date_format": "dd.mm.yyyy",
	"time_format": "HH:mm",
	"first_day_of_the_week": "Monday",
	"float_precision": "2",
	"currency_precision": "2",
}


class TestTurkeySetup(IntegrationTestCase):
	def test_hooks_are_registered(self):
		hook = "platform_core.config.turkey_setup.apply"
		self.assertEqual(frappe.get_hooks("setup_wizard_complete").count(hook), 1)
		self.assertEqual(frappe.get_hooks("after_migrate").count(hook), 1)

	def test_defaults_replace_wizard_values_and_second_run_is_a_no_op(self):
		# The setup wizard writes float_precision=3 and an empty date format for Türkiye.
		frappe.db.set_single_value("System Settings", {"float_precision": "3", "date_format": "mm-dd-yyyy"})
		turkey_setup.apply({"country": "Türkiye"})

		settings = frappe.get_single("System Settings")
		for field, value in EXPECTED.items():
			with self.subTest(field=field):
				self.assertEqual(str(settings.get(field)), value)
				self.assertEqual(frappe.db.get_default(field), value)
		self.assertEqual(frappe.db.get_default("lang"), "tr")
		if "erpnext" in frappe.get_installed_apps():
			self.assertEqual(frappe.db.get_single_value("Global Defaults", "country"), "Türkiye")
			self.assertEqual(frappe.db.get_single_value("Global Defaults", "default_currency"), "TRY")
			self.assertEqual(frappe.db.get_value("Currency", "TRY", "enabled"), 1)

		modified = frappe.db.get_single_value("System Settings", "modified")
		turkey_setup.apply()
		self.assertEqual(frappe.db.get_single_value("System Settings", "modified"), modified)
