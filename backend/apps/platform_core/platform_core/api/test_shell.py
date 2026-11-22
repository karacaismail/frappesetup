import json
from unittest.mock import patch
from urllib.parse import quote, urlencode

import frappe
from frappe.core.doctype.user.user import generate_keys

from platform_core.kabuk.bootstrap import get_bootstrap, safe_url
from platform_core.tests.shell_http_fixture import DOCTYPE, PRIVILEGED, READER, ShellHTTPFixture


class TestBootstrapHTTP(ShellHTTPFixture):
	def test_get_bootstrap_guest_denied(self):
		status, _, _ = self.request("/api/method/platform_core.api.shell.get_bootstrap")
		self.assertEqual(status, 403)

	def test_session_id_in_query_does_not_replace_cookie(self):
		query = urlencode({"sid": self.reader_sid})
		status, _, _ = self.request("/api/method/platform_core.api.shell.get_bootstrap?" + query)
		self.assertEqual(status, 403)

	def test_get_bootstrap_foreign_data_denied(self):
		status, _, body = self.request("/api/method/platform_core.api.shell.get_bootstrap", self.reader_sid)
		self.assertEqual(status, 200)
		payload = json.loads(body)["message"]
		self.assertEqual(payload["user"]["name"], READER)
		self.assertIn("platform_core", payload["installed_apps"])
		names = [page["name"] for page in payload["workspaces"]]
		self.assertIn("Kabuk Visible", names)
		self.assertNotIn("Kabuk Hidden", names)
		self.assertNotIn("Kabuk Restricted", names)
		self.assertNotIn("Kabuk Hidden", json.dumps(payload["sidebars"]))
		self.assertNotIn("Kabuk Restricted", json.dumps(payload["sidebars"]))

	def test_sidebar_includes_own_private_workspace_only(self):
		status, _, body = self.request("/api/method/platform_core.api.shell.get_bootstrap", self.reader_sid)
		self.assertEqual(status, 200)
		sidebars = json.loads(body)["message"]["sidebars"]
		targets = {item.get("link_to") for sidebar in sidebars for item in sidebar["data"]["items"]}
		self.assertIn("Kabuk Reader Private", targets)
		self.assertNotIn("Kabuk Other Private", targets)

	def test_api_key_does_not_create_browser_session(self):
		keys = generate_keys(READER)
		frappe.db.commit()
		headers = {"Authorization": f"token {keys['api_key']}:{keys['api_secret']}"}
		try:
			status, _, _ = self.request("/api/method/frappe.auth.get_logged_user", headers=headers)
			self.assertEqual(status, 200)
			status, _, _ = self.request("/api/method/platform_core.api.shell.get_bootstrap", headers=headers)
			self.assertEqual(status, 403)
			status, _, _ = self.request(f"/api/v2/doctype/{quote(DOCTYPE)}/meta", headers=headers)
			self.assertEqual(status, 403)
			status, _, _ = self.request("/panel", headers=headers)
			self.assertEqual(status, 302)
		finally:
			frappe.db.rollback()
			frappe.db.set_value("User", READER, "api_key", None, update_modified=False)
			frappe.db.commit()

	def test_direct_bootstrap_cannot_switch_users(self):
		frappe.set_user(READER)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_bootstrap(PRIVILEGED)
		finally:
			frappe.set_user("Administrator")

	def test_workspace_manager_cannot_see_hidden_or_unsafe_navigation(self):
		user = frappe.get_doc("User", READER)
		user.append("roles", {"role": "Workspace Manager"})
		user.save()
		frappe.db.commit()
		try:
			sid = self.login(READER)
			status, _, body = self.request("/api/method/platform_core.api.shell.get_bootstrap", sid)
			self.assertEqual(status, 200)
			payload = json.loads(body)["message"]
			self.assertIn("Workspace Manager", payload["user"]["roles"])
			self.assertIn("Kabuk Visible", body.decode("utf-8"))
			self.assertIn("Shell Safe Link", body.decode("utf-8"))
			for target in ("Kabuk Hidden", "Shell Unsafe Shortcut", "Shell Unsafe Link", "javascript:"):
				self.assertNotIn(target, body.decode("utf-8"))
		finally:
			frappe.db.rollback()
			user = frappe.get_doc("User", READER)
			user.set("roles", [{"role": "Kabuk Test Reader"}])
			user.save()
			frappe.db.commit()

	def test_safe_url_rejects_disallowed_links(self):
		for url in (
			"javascript:void(0)",
			"JAVASCRIPT:void(0)",
			"data:text/plain,example",
			"//example.test/path",
			"/\\example.test",
			"https:example.test",
		):
			with self.subTest(url=url):
				self.assertFalse(safe_url(url))
		self.assertTrue(safe_url("/panel"))
		self.assertFalse(safe_url("https://example.test/panel"))
		with patch.dict(frappe.conf, {"shell_navigation_hosts": ["example.test"], "developer_mode": False}):
			self.assertTrue(safe_url("https://example.test/panel"))
			self.assertTrue(safe_url("HTTPS://example.test/panel"))
			self.assertFalse(safe_url("http://example.test/panel"))
			self.assertFalse(safe_url("https://sub.example.test/panel"))
			self.assertFalse(safe_url("https://example.test@external.test/panel"))
		with patch.dict(frappe.conf, {"shell_navigation_hosts": ["example.test"], "developer_mode": True}):
			self.assertTrue(safe_url("http://example.test/panel"))

	def test_bootstrap_includes_formatting_settings(self):
		status, _, body = self.request("/api/method/platform_core.api.shell.get_bootstrap", self.reader_sid)
		self.assertEqual(status, 200)
		formatting = json.loads(body)["message"]["formatting"]
		for key in ("time_zone", "number_format", "rounding_method"):
			self.assertTrue(formatting[key])
		self.assertEqual(formatting["currency"], frappe.get_system_settings("currency") or None)

	def test_sidebar_drops_unknown_fields(self):
		from platform_core.kabuk.bootstrap import project_sidebar

		data = project_sidebar(
			{
				"name": "Example",
				"internal": "ignore",
				"items": [
					{
						"type": "Link",
						"link_type": "DocType",
						"link_to": DOCTYPE,
						"new_key": "ignore",
						"url": "javascript:void(0)",
						"report": {"report_type": "Script Report", "private": "ignore"},
					}
				],
			}
		)
		self.assertNotIn("internal", data)
		self.assertNotIn("new_key", data["items"][0])
		self.assertNotIn("url", data["items"][0])
		self.assertEqual(data["items"][0]["report"], {"report_type": "Script Report"})

	def test_session_probe_and_shell_distinguish_guest_and_expired_sessions(self):
		from frappe.sessions import delete_session

		sid = self.login(READER)
		probe = "/api/method/frappe.auth.get_logged_user"
		status, _, body = self.request(probe, sid)
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(body)["message"], READER)
		delete_session(sid=sid)
		frappe.db.commit()
		for path in (probe, "/api/method/platform_core.api.shell.get_bootstrap"):
			self.assertEqual(self.request(path)[0], 403)
			self.assertEqual(self.request(path, sid)[0], 401)
		self.assertEqual(self.metadata(sid)[0], 401)

	def test_shell_requests_refuse_unknown_parameters(self):
		paths = (
			"/api/method/platform_core.api.shell.get_bootstrap?",
			"/api/method/platform_core.api.meta.get_doctype?" + urlencode({"doctype": DOCTYPE}) + "&",
		)
		for path in paths:
			for key in ("role", "user", "ignore_permissions"):
				with self.subTest(path=path, key=key):
					status, _, body = self.request(
						path + urlencode({key: "forbidden-user-marker"}), self.reader_sid
					)
					self.assertEqual(status, 417)
					self.assertEqual(json.loads(body)["exc_type"], "ValidationError")
					self.assertNotIn(b"forbidden-user-marker", body)

	def test_metadata_missing_doctype_is_a_validation_error(self):
		status, _, body = self.request("/api/method/platform_core.api.meta.get_doctype", self.reader_sid)
		self.assertEqual(status, 417)
		self.assertEqual(json.loads(body)["exc_type"], "ValidationError")

	def test_shell_rate_limits_apply_per_account_and_endpoint(self):
		for suffix, limit in (("shell.get_bootstrap", 120), ("meta.get_doctype", 240)):
			with self.subTest(endpoint=suffix):
				endpoint = f"platform_core.api.{suffix}"
				path = f"/api/method/{endpoint}"
				if suffix == "meta.get_doctype":
					path += "?" + urlencode({"doctype": DOCTYPE})
				key = frappe.cache.make_key(f"rl:{endpoint}:{READER}") + b":60"
				frappe.cache.setex(key, 60, limit - 1)
				try:
					self.assertEqual(self.request(path, self.reader_sid)[0], 200)
					status, _, body = self.request(path, self.reader_sid)
					self.assertEqual(status, 429)
					self.assertEqual(json.loads(body)["exc_type"], "RateLimitExceededError")
					self.assertEqual(self.request(path, self.privileged_sid)[0], 200)
				finally:
					frappe.cache.delete(key)
