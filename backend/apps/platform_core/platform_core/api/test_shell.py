import json

from platform_core.kabuk.http_fixture import DOCTYPE, PRIVILEGED, READER, ShellHTTPFixture


class TestBootstrapHTTP(ShellHTTPFixture):
	def test_get_bootstrap_guest_denied(self):
		status, _, _ = self.request("/api/method/platform_core.api.shell.get_bootstrap")
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
