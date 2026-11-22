"""Exercise the documented G-12 routes on the isolated Press site."""

import http.client
import json
import os
import unittest
from urllib.parse import parse_qs, urlsplit

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
	def exchange(self, method, path, headers=None, body=None):
		port = int(os.environ["PANE_PORT"]) + 3
		connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
		try:
			connection.request(
				method, path, body=body, headers={"Host": "press.localhost", **(headers or {})}
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
		self.assertTrue(
			any(
				cookie.startswith(f"press_tr_login={query['state'][0]};")
				for cookie in headers.get_all("Set-Cookie")
			)
		)
		status, _ = self.request(
			"GET", f"/api/method/press_tr.api.auth.keycloak_callback?state={query['state'][0]}&code=unused"
		)
		self.assertEqual(status, 403)

	def test_disabled_endpoints(self):
		for command in CLOSED_METHODS:
			with self.subTest(command=command):
				status, _ = self.request("POST", f"/api/method/{command}")
				self.assertEqual(status, 403)

	def test_legacy_pages_redirect_to_panel(self):
		for path in ("/login", "/signup", "/dashboard/login"):
			with self.subTest(path=path):
				status, location = self.request("GET", path)
				self.assertEqual(status, 302)
				self.assertEqual(location, os.environ["PRESS_TEST_PANEL_URL"])


if __name__ == "__main__":
	unittest.main()
