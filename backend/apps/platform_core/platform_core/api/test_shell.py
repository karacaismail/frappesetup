import json
from urllib.parse import urlencode

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
		for url in ("javascript:void(0)", "//example.test/path", "/\\example.test"):
			with self.subTest(url=url):
				self.assertFalse(safe_url(url))
		self.assertTrue(safe_url("/panel"))
		self.assertTrue(safe_url("https://example.test/panel"))
