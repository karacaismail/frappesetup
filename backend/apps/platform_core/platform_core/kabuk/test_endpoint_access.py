"""Exercise each shell route with real Frappe sessions and permission checks."""

import json
from urllib.parse import quote, urlencode

import frappe

from platform_core.kabuk.test_panel import PanelMetadata
from platform_core.tests.shell_http_fixture import DOCTYPE, READER, ShellHTTPFixture

DESK_WITHOUT_RECORD_ROLE = "shell-desk-without-record-role@example.test"
SYSTEM_MANAGER = "shell-system-manager@example.test"
BOOTSTRAP = "/api/method/platform_core.api.shell.get_bootstrap"
METADATA = "/api/method/platform_core.api.meta.get_doctype"
POLICY_CHECK = "/api/method/platform_core.api.meta.validate_mobile_policy"
SESSION_PROBE = "/api/method/frappe.auth.get_logged_user"
NATIVE_METADATA = "/api/v2/doctype/{doctype}/meta"
MISSING_DOCTYPE = "Shell Missing Matrix DocType"


class TestShellEndpointAccess(ShellHTTPFixture):
	additional_users = (
		(DESK_WITHOUT_RECORD_ROLE, ["Shell Test Desk"]),
		(SYSTEM_MANAGER, ["System Manager"]),
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.sessions = (
			("Guest", None),
			(READER, cls.reader_sid),
			(DESK_WITHOUT_RECORD_ROLE, cls.login(DESK_WITHOUT_RECORD_ROLE)),
			(SYSTEM_MANAGER, cls.login(SYSTEM_MANAGER)),
		)

	def test_fixture_roles_match_the_access_matrix(self):
		desk = frappe.get_doc("User", DESK_WITHOUT_RECORD_ROLE)
		self.assertEqual(desk.user_type, "System User")
		self.assertEqual({item.role for item in desk.roles}, {"Shell Test Desk"})
		manager = frappe.get_doc("User", SYSTEM_MANAGER)
		self.assertEqual(manager.user_type, "System User")
		self.assertEqual({item.role for item in manager.roles}, {"System Manager"})
		self.assertEqual(frappe.db.get_value("User", READER, "user_type"), "Website User")
		self.assertFalse(frappe.db.exists("DocType", MISSING_DOCTYPE))

	def check_json_access(self, route, statuses):
		native = route.startswith("/api/v2/")
		key = "data" if native else "message"
		authorized = []
		for (account, sid), expected in zip(self.sessions, statuses, strict=True):
			with self.subTest(route=route, account=account):
				status, _unused_headers, body = self.request(route, sid)
				self.assertEqual(status, expected)
				payload = json.loads(body)
				if expected == 200:
					authorized.append((account, payload[key]))
				else:
					self.assertNotIn(key, payload)
					error = "PermissionError" if expected == 403 else "DoesNotExistError"
					if native:
						self.assertEqual([item["type"] for item in payload["errors"]], [error])
					else:
						self.assertEqual(payload["exc_type"], error)
		return authorized

	def test_bootstrap_requires_a_session_and_returns_that_account(self):
		for account, payload in self.check_json_access(BOOTSTRAP, (403, 200, 200, 200)):
			self.assertEqual(payload["user"]["name"], account)

	def test_metadata_requires_read_permission(self):
		for doctype, statuses in ((DOCTYPE, (403, 200, 403, 403)), ("Role", (403, 403, 403, 200))):
			route = METADATA + "?" + urlencode({"doctype": doctype})
			for _unused_account, payload in self.check_json_access(route, statuses):
				self.assertEqual(payload["schema"]["name"], doctype)

	def test_mobile_policy_requires_system_manager(self):
		for _unused_account, payload in self.check_json_access(POLICY_CHECK, (403, 403, 403, 200)):
			self.assertEqual(payload, {"valid": True, "errors": []})

	def test_panel_requires_a_session(self):
		for (account, sid), expected in zip(self.sessions, (302, 200, 200, 200), strict=True):
			with self.subTest(account=account):
				status, headers, body = self.request("/panel", sid)
				self.assertEqual(status, expected)
				self.assertIn("no-store", headers["Cache-Control"])
				token = PanelMetadata(body).token
				if expected == 302:
					self.assertEqual(headers["Location"], "/login?redirect-to=/panel")
					self.assertIsNone(token)
				else:
					self.assertTrue(token)

	def test_native_metadata_requires_desk_access(self):
		for doctype, statuses in (("Role", (403, 403, 200, 200)), (MISSING_DOCTYPE, (403, 403, 403, 404))):
			route = NATIVE_METADATA.format(doctype=quote(doctype))
			for _unused_account, payload in self.check_json_access(route, statuses):
				self.assertEqual(payload["name"], doctype)

	def test_session_probe_requires_a_session_and_returns_that_account(self):
		for account, payload in self.check_json_access(SESSION_PROBE, (403, 200, 200, 200)):
			self.assertEqual(payload, account)
