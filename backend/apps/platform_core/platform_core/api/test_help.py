"""G-138 help endpoints over the real HTTP path, with a field at permission level 1."""

import json
from urllib.parse import urlencode

import frappe

from platform_core.tests.shell_http_fixture import DOCTYPE, ShellHTTPFixture

FIELD_HELP = "/api/method/platform_core.api.help.get_field_help"
COVERAGE = "/api/method/platform_core.api.help.get_help_coverage"
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
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.delete("PLT Help Topic", {"document_type": DOCTYPE})
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
