"""G-40: with developer mode off, the schema comes only from app code.

Frappe skips its developer mode check while tests run. The test turns the test flag off
for one call, so the check runs as it does on a tenant site.
"""

from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.core.doctype.doctype.doctype import CannotCreateStandardDoctypeError
from frappe.tests import IntegrationTestCase

APP_ROOT = Path(frappe.get_app_path("platform_core")).parent


def app_files():
	return {path: path.stat().st_mtime_ns for path in APP_ROOT.rglob("*") if path.is_file()}


class TestSchemaSource(IntegrationTestCase):
	def tenant_mode(self):
		return patch.multiple(frappe, in_test=False), patch.dict(frappe.conf, {"developer_mode": 0})

	def test_standard_doctype_is_refused_without_developer_mode(self):
		doc = frappe.get_doc(
			{
				"doctype": "DocType",
				"name": "PLT Schema Source Probe",
				"module": "Identity",
				"custom": 0,
				"fields": [{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
				"permissions": [{"role": "System Manager", "read": 1}],
			}
		)
		test_flag, conf = self.tenant_mode()
		with test_flag, conf, self.assertRaises(CannotCreateStandardDoctypeError):
			doc.insert()
		self.assertFalse(frappe.db.exists("DocType", "PLT Schema Source Probe"))

	def test_custom_field_is_saved_in_the_database_only(self):
		before = app_files()
		test_flag, conf = self.tenant_mode()
		with test_flag, conf:
			field = frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "ToDo",
					"fieldname": "plt_schema_source_probe",
					"fieldtype": "Data",
					"label": "Schema Source Probe",
				}
			).insert()
		self.addCleanup(frappe.delete_doc, "Custom Field", field.name, force=True)
		self.assertTrue(frappe.db.exists("Custom Field", field.name))
		self.assertEqual(app_files(), before)
