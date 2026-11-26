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

	def test_unsafe_help_links_cannot_be_saved(self):
		for fieldname in ("tour_url", "doc_url", "support_url"):
			for value in ("javascript:alert(1)", "//example.test", "/\\example.test", "http://example.test"):
				with self.subTest(fieldname=fieldname, value=value):
					record = self.add_topic(OPEN_FIELD)
					record.set(fieldname, value)
					with self.assertRaises(frappe.ValidationError):
						record.save()

	def test_blank_help_links_are_normalized_and_safe_links_are_saved(self):
		record = self.add_topic(OPEN_FIELD)
		record.update(
			{"tour_url": "  ", "doc_url": "https://docs.example.test/guide", "support_url": "/support"}
		)
		record.save()
		record.reload()
		self.assertFalse(record.tour_url)
		frappe.set_user(USER)
		answer = get_field_help(DOCTYPE, OPEN_FIELD, USER, "en")
		self.assertIsNone(answer["tour_url"])
		self.assertEqual(answer["doc_url"], "https://docs.example.test/guide")
		self.assertEqual(answer["support_url"], "/support")

	def test_readable_field_returns_the_tenant_topic(self):
		record = self.add_topic(OPEN_FIELD)
		frappe.set_user(USER)
		answer = get_field_help(DOCTYPE, OPEN_FIELD, USER, "en")
		self.assertEqual(answer["source"], "tenant")
		self.assertEqual(answer["topic"], record.name)
		self.assertEqual(answer["content"], f"Tenant help for {OPEN_FIELD}.")

	def test_readable_field_falls_back_to_its_description(self):
		frappe.set_user(USER)
		answer = get_field_help(DOCTYPE, OPEN_FIELD, USER, "en")
		self.assertEqual(answer["source"], "description")
		self.assertEqual(answer["content"], f"Description of {OPEN_FIELD}.")

	def test_field_at_an_unreadable_level_returns_no_help(self):
		self.add_topic(CLOSED_FIELD)
		frappe.set_user(USER)
		answer = get_field_help(DOCTYPE, CLOSED_FIELD, USER, "en")
		self.assertEqual(answer["source"], "unavailable")
		self.assertIsNone(answer["content"])

	def test_unknown_field_looks_like_an_unreadable_field(self):
		frappe.set_user(USER)
		answer = get_field_help(DOCTYPE, "no_such_field", USER, "en")
		self.assertEqual(answer["source"], "unavailable")

	def test_coverage_report_is_for_the_system_manager(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			get_help_coverage("frappe")

	def test_coverage_report_counts_the_custom_fields(self):
		self.add_topic(OPEN_FIELD)
		report = get_help_coverage("frappe")
		self.assertGreater(report["total"], 0)
		self.assertNotIn({"doctype": DOCTYPE, "fieldname": OPEN_FIELD, "is_custom": True}, report["missing"])


class TestHelpHooks(IntegrationTestCase):
	def test_website_users_reach_field_help_but_not_the_coverage_report(self):
		allowed = frappe.get_hooks("website_user_allowed_methods")
		self.assertIn("platform_core.api.help.get_field_help", allowed)
		self.assertIn("platform_core.api.help.get_component_help", allowed)
		self.assertNotIn("platform_core.api.help.get_help_coverage", allowed)
		for name in ("get_field_help", "get_component_help", "get_help_coverage"):
			self.assertIn(frappe.get_attr(f"platform_core.api.help.{name}"), frappe.whitelisted, name)
