import json
from urllib.parse import urlencode

import frappe
from frappe.core.doctype.user.user import generate_keys

from platform_core.kabuk.http_fixture import DOCTYPE, PRIVILEGED, READER, ShellHTTPFixture


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
