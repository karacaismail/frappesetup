"""G-138 help endpoints over the real HTTP path, with a field at permission level 1."""

import json
import os
from urllib.parse import urlencode

import frappe

from platform_core.tests.shell_http_fixture import DOCTYPE, ShellHTTPFixture

FIELD_HELP = "/api/method/platform_core.api.help.get_field_help"
COVERAGE = "/api/method/platform_core.api.help.get_help_coverage"
COMPONENT_HELP = "/api/method/platform_core.api.help.get_component_help"
COMPONENT_ID = "test-private-component"
PRIVATE_HELP = "Tenant help for the private note."


class TestHelpHTTP(ShellHTTPFixture):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.delete("PLT Help Topic", {"document_type": DOCTYPE})
		frappe.get_doc(
			{
				"doctype": "PLT Help Topic",
				"title": "Private note",
				"layer": "Tenant",
				"target_type": "Field",
				"document_type": DOCTYPE,
				"fieldname": "private_note",
				"status": "Published",
				"content": PRIVATE_HELP,
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "PLT Help Topic",
				"title": "Private component",
				"layer": "Tenant",
				"target_type": "Component",
				"component_id": COMPONENT_ID,
				"status": "Published",
				"target_roles": [{"role": "Shell Test Desk"}],
				"content": PRIVATE_HELP,
				"tour_url": "/test-tour",
				"doc_url": "https://docs.example.test/private",
				"support_url": "/test-support",
			}
		).insert()
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.delete("PLT Help Topic", {"document_type": DOCTYPE})
		frappe.db.delete("PLT Help Topic", {"component_id": COMPONENT_ID})
		frappe.db.commit()
		super().tearDownClass()

	def field_help(self, sid, fieldname):
		return self.request(FIELD_HELP + "?" + urlencode({"doctype": DOCTYPE, "fieldname": fieldname}), sid)

	def test_get_field_help_guest_denied(self):
		status, _unused_headers, body = self.field_help(None, "private_note")
		self.assertEqual(status, 403)
		self.assertNotIn(PRIVATE_HELP, body.decode())

	def test_get_field_help_foreign_data_denied(self):
		# The desk user reads level 1, so the topic is shown.
		status, _unused_headers, body = self.field_help(self.desk_sid, "private_note")
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(body)["message"]["source"], "tenant")
		# The reader cannot read level 1, so neither the topic nor the description is shown.
		status, _unused_headers, body = self.field_help(self.reader_sid, "private_note")
		self.assertEqual(status, 200)
		message = json.loads(body)["message"]
		self.assertEqual(message["source"], "unavailable")
		self.assertIsNone(message["content"])
		self.assertNotIn(PRIVATE_HELP, body.decode())
		self.assertNotIn("Restricted note.", body.decode())

	def test_readable_field_falls_back_to_its_description_over_http(self):
		status, _unused_headers, body = self.field_help(self.reader_sid, "title")
		self.assertEqual(status, 200)
		message = json.loads(body)["message"]
		self.assertEqual((message["source"], message["content"]), ("description", "Public title."))

	def test_unknown_parameters_are_rejected(self):
		status, _unused_headers, _unused_body = self.request(
			FIELD_HELP + "?" + urlencode({"doctype": DOCTYPE, "fieldname": "title", "extra": "1"}),
			self.reader_sid,
		)
		self.assertEqual(status, 417)

	def test_get_help_coverage_guest_denied(self):
		status, _unused_headers, _unused_body = self.request(COVERAGE + "?app=platform_core")
		self.assertEqual(status, 403)

	def test_get_help_coverage_foreign_data_denied(self):
		# A desk user without the System Manager role cannot read the site-wide report.
		status, _unused_headers, body = self.request(COVERAGE + "?app=platform_core", self.desk_sid)
		self.assertEqual(status, 403)
		self.assertNotIn("missing", body.decode())

	def test_get_component_help_guest_denied(self):
		status, _headers, body = self.request(COMPONENT_HELP + "?component_id=" + COMPONENT_ID)
		self.assertEqual(status, 403)
		self.assertNotIn(PRIVATE_HELP, body.decode())

	def test_get_component_help_foreign_data_denied(self):
		path = COMPONENT_HELP + "?component_id=" + COMPONENT_ID
		status, _headers, body = self.request(path, self.desk_sid)
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(body)["message"]["doc_url"], "https://docs.example.test/private")
		status, _headers, body = self.request(path, self.reader_sid)
		self.assertEqual(status, 200)
		self.assertIsNone(json.loads(body)["message"])
		self.assertNotIn(PRIVATE_HELP, body.decode())
		# A request cannot select a different tenant or impersonate another user.
		for parameter in ("tenant", "site", "user"):
			status, _headers, body = self.request(path + "&" + parameter + "=other", self.reader_sid)
			self.assertEqual(status, 417)
			self.assertNotIn(PRIVATE_HELP, body.decode())

	def test_missing_component_returns_empty_help(self):
		status, _headers, body = self.request(
			COMPONENT_HELP + "?component_id=no-such-component", self.reader_sid
		)
		self.assertEqual(status, 200)
		self.assertIsNone(json.loads(body)["message"])

	def test_component_session_cannot_read_another_tenant_site(self):
		foreign_site = os.environ.get("PLT_HELP_FOREIGN_TEST_SITE")
		if not foreign_site:
			self.skipTest("Set PLT_HELP_FOREIGN_TEST_SITE to run the two-site session check.")
		self.assertEqual(foreign_site, "test-help-foreign.localhost")
		status, _headers, body = self.request(
			COMPONENT_HELP + "?component_id=" + COMPONENT_ID,
			self.desk_sid,
			headers={"Host": foreign_site},
		)
		self.assertIn(status, (401, 403))
		self.assertNotIn(PRIVATE_HELP, body.decode())
		self.assertNotIn("https://docs.example.test/private", body.decode())

	def test_same_component_identifier_keeps_each_tenants_content_separate(self):
		foreign_site = os.environ.get("PLT_HELP_FOREIGN_TEST_SITE")
		if not foreign_site:
			self.skipTest("Set PLT_HELP_FOREIGN_TEST_SITE to run the two-site content check.")
		self.assertEqual(foreign_site, "test-help-foreign.localhost")
		primary_site = self.site
		foreign_user = "foreign-help-reader@example.test"
		foreign_content = "Component help from the other tenant."
		try:
			frappe.destroy()
			frappe.init(site=foreign_site, sites_path=os.getcwd())
			frappe.connect()
			self.assertTrue(frappe.conf.allow_tests)
			frappe.set_user("Administrator")
			if not frappe.db.exists("User", foreign_user):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": foreign_user,
						"first_name": "Foreign help reader",
						"send_welcome_email": 0,
						"new_password": self.password,
						"roles": [{"role": "Desk User"}],
					}
				).insert()
			else:
				from frappe.utils.password import update_password

				update_password(foreign_user, self.password)
			frappe.db.delete("PLT Help Topic", {"component_id": COMPONENT_ID})
			frappe.get_doc(
				{
					"doctype": "PLT Help Topic",
					"title": "Foreign component",
					"layer": "Tenant",
					"target_type": "Component",
					"component_id": COMPONENT_ID,
					"status": "Published",
					"content": foreign_content,
					"doc_url": "/foreign-docs",
				}
			).insert()
			frappe.db.commit()
			type(self).site = foreign_site
			foreign_sid = self.login(foreign_user)
			path = COMPONENT_HELP + "?component_id=" + COMPONENT_ID
			status, _headers, body = self.request(path, foreign_sid)
			self.assertEqual(status, 200)
			self.assertEqual(json.loads(body)["message"]["content"], foreign_content)
			self.assertEqual(json.loads(body)["message"]["doc_url"], "/foreign-docs")
			self.assertNotIn(PRIVATE_HELP, body.decode())
			type(self).site = primary_site
			status, _headers, body = self.request(path, self.desk_sid)
			self.assertEqual(status, 200)
			self.assertEqual(json.loads(body)["message"]["content"], PRIVATE_HELP)
			self.assertNotIn(foreign_content, body.decode())
			self.assertNotIn("/foreign-docs", body.decode())
		finally:
			type(self).site = primary_site
			if frappe.local.site == foreign_site:
				frappe.set_user("Administrator")
				frappe.db.delete("PLT Help Topic", {"component_id": COMPONENT_ID})
				frappe.db.commit()
			frappe.destroy()
			frappe.init(site=primary_site, sites_path=os.getcwd())
			frappe.connect()
			frappe.set_user("Administrator")

	def test_component_input_is_validated(self):
		for query in (
			"",
			"?component_id=",
			"?component_id=" + "x" * 141,
			"?component_id=ok&language=" + "x" * 21,
		):
			status, _headers, _body = self.request(COMPONENT_HELP + query, self.reader_sid)
			self.assertEqual(status, 417)
