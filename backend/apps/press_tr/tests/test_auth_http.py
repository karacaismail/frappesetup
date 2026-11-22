"""Exercise the documented G-12 routes on the isolated Press site."""

import http.client
import json
import os
import unittest
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

ACCOUNT_METHODS = (
	"signup",
	"send_otp",
	"verify_otp",
	"verify_otp_and_login",
	"send_login_link",
	"login_using_key",
	"reset_password",
	"enable_2fa",
	"verify_2fa",
)
CLOSED_METHODS = (
	*(f"press.api.account.{name}" for name in ACCOUNT_METHODS),
	"press.api.product_trial.send_verification_code_for_login",
)


class PressHttpClient:
	def setUp(self):
		octets = uuid4().bytes
		self.request_ip = f"198.18.{octets[0]}.{octets[1]}"

	def exchange(self, method, path, headers=None, body=None):
		port = int(os.environ["PANE_PORT"]) + 3
		connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
		try:
			connection.request(
				method,
				path,
				body=body,
				headers={"Host": "press.localhost", "X-Forwarded-For": self.request_ip, **(headers or {})},
			)
			response = connection.getresponse()
			return response.status, response.headers, response.read()
		finally:
			connection.close()

	def request(self, method, path):
		status, headers, _ = self.exchange(method, path)
		return status, headers.get("Location")


class AuthHttpTest(PressHttpClient, unittest.TestCase):
	def test_login_url_uses_server_generated_values(self):
		status, headers, payload = self.exchange("POST", "/api/method/press_tr.api.auth.get_login_url")
		self.assertEqual(status, 200)
		url = urlsplit(json.loads(payload)["message"]["url"])
		self.assertTrue(url.path.endswith("/protocol/openid-connect/auth"))
		query = parse_qs(url.query)
		self.assertEqual(query["code_challenge_method"], ["S256"])
		for key in ("state", "nonce", "code_challenge"):
			self.assertGreaterEqual(len(query[key][0]), 43)
		cookies = SimpleCookie()
		for header in headers.get_all("Set-Cookie"):
			cookies.load(header)
		browser = cookies["press_tr_login"]
		self.assertEqual(len(browser.value), 43)
		self.assertNotEqual(browser.value, query["state"][0])
		self.assertTrue(browser["httponly"])
		self.assertEqual(browser["samesite"], "Lax")
		self.assertEqual(browser["max-age"], "600")
		status, _ = self.request(
			"GET", f"/api/method/press_tr.api.auth.keycloak_callback?state={query['state'][0]}&code=unused"
		)
		self.assertEqual(status, 403)

	def test_guest_contract_allows_ping_and_rejects_other_rpc(self):
		for prefix in ("/api/method/", "/api/v1/method/", "/api/v2/method/"):
			with self.subTest(prefix=prefix):
				self.assertEqual(self.request("GET", prefix + "ping")[0], 200)
				self.assertEqual(self.request("GET", prefix + "frappe.utils.get_url")[0], 403)

	def test_disabled_endpoints(self):
		for command in CLOSED_METHODS:
			with self.subTest(command=command):
				status, _ = self.request("POST", f"/api/method/{command}")
				self.assertEqual(status, 403)

	def test_canonical_rpc_versions_block_legacy_identity(self):
		for prefix in ("/api/method/", "/api/v1/method/", "/api/v2/method/"):
			for command in (
				*CLOSED_METHODS,
				"login",
				"frappe.integrations.oauth2_logins.login_via_google",
				"frappe.core.doctype.user.user.reset_password",
				"frappe.core.doctype.user.user.update_password",
				"frappe.www.login.login_via_token",
				"frappe.www.login.login_via_key",
				"frappe.www.login.send_login_link",
				"press.api.account.setup_account",
				"press.api.oauth.google_login",
			):
				with self.subTest(prefix=prefix, command=command):
					status, _ = self.request("POST", prefix + command)
					self.assertEqual(status, 403)

	def test_login_url_rate_limit(self):
		path = "/api/method/press_tr.api.auth.get_login_url"
		for _ in range(10):
			self.assertEqual(self.request("POST", path)[0], 200)
		self.assertEqual(self.request("POST", path)[0], 429)

	def test_legacy_pages_redirect_to_panel(self):
		for path in ("/login", "/signup", "/dashboard/login"):
			with self.subTest(path=path):
				status, location = self.request("GET", path)
				self.assertEqual(status, 302)
				self.assertEqual(location, os.environ["PRESS_TEST_PANEL_URL"])


if __name__ == "__main__":
	unittest.main()
