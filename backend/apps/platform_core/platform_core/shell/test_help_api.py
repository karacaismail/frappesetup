"""G-138: field help on a real site, with Frappe's own field permission levels."""

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.shell.help import get_field_help, get_help_coverage

DOCTYPE = "ToDo"
USER = "help-reader@example.com"
OPEN_FIELD = "custom_help_open"
CLOSED_FIELD = "custom_help_closed"


class TestFieldHelp(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		for fieldname, permlevel in ((OPEN_FIELD, 0), (CLOSED_FIELD, 1)):
			if not frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": fieldname}):
				frappe.get_doc(
					{
						"doctype": "Custom Field",
						"dt": DOCTYPE,
						"fieldname": fieldname,
						"label": fieldname,
						"fieldtype": "Data",
						"permlevel": permlevel,
						"description": f"Description of {fieldname}.",
						"insert_after": "description",
					}
				).insert()
		if not frappe.db.exists("User", USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": USER,
					"first_name": "Help Reader",
					"send_welcome_email": 0,
					"roles": [{"role": "Desk User"}],
				}
			).insert()
		frappe.clear_cache(doctype=DOCTYPE)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("PLT Help Topic", {"document_type": DOCTYPE})

	def tearDown(self):
		frappe.set_user("Administrator")

	def add_topic(self, fieldname, status="Published"):
		return frappe.get_doc(
			{
				"doctype": "PLT Help Topic",
				"title": f"Help for {fieldname}",
				"layer": "Tenant",
				"target_type": "Field",
				"document_type": DOCTYPE,
				"fieldname": fieldname,
				"status": status,
				"content": f"Tenant help for {fieldname}.",
			}
		).insert()

	def test_topic_fills_the_application_of_its_document_type(self):
		record = self.add_topic(OPEN_FIELD)
		self.assertEqual(record.app, "frappe")

	def test_topic_on_a_missing_field_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.add_topic("no_such_field")

	def test_readable_field_returns_the_tenant_topic(self):
		record = self.add_topic(OPEN_FIELD)
		frappe.set_user(USER)
		result = get_field_help(DOCTYPE, OPEN_FIELD, USER, "en")
		self.assertEqual(result["source"], "tenant")
		self.assertEqual(result["topic"], record.name)
		self.assertEqual(result["content"], f"Tenant help for {OPEN_FIELD}.")

	def test_readable_field_falls_back_to_its_description(self):
		frappe.set_user(USER)
		result = get_field_help(DOCTYPE, OPEN_FIELD, USER, "en")
		self.assertEqual(result["source"], "description")
		self.assertEqual(result["content"], f"Description of {OPEN_FIELD}.")

	def test_field_at_an_unreadable_level_returns_no_help(self):
		self.add_topic(CLOSED_FIELD)
		frappe.set_user(USER)
		result = get_field_help(DOCTYPE, CLOSED_FIELD, USER, "en")
		self.assertEqual(result["source"], "unavailable")
		self.assertIsNone(result["content"])

	def test_unknown_field_looks_like_an_unreadable_field(self):
		frappe.set_user(USER)
		result = get_field_help(DOCTYPE, "no_such_field", USER, "en")
		self.assertEqual(result["source"], "unavailable")

	def test_coverage_report_is_for_the_system_manager(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			get_help_coverage("frappe")

	def test_coverage_report_counts_the_custom_fields(self):
		self.add_topic(OPEN_FIELD)
		report = get_help_coverage("frappe")
		self.assertGreater(report["total"], 0)
		self.assertNotIn(
			{"doctype": DOCTYPE, "fieldname": OPEN_FIELD, "is_custom": True}, report["missing"]
		)
