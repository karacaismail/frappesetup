"""Check the security headers on actual Frappe HTTP responses."""

from http.cookies import SimpleCookie

import frappe

from platform_core.tests.shell_http_fixture import DESK, ShellHTTPFixture

BOOTSTRAP = "/api/method/platform_core.api.shell.get_bootstrap"
CSP = "Content-Security-Policy"
BASE_POLICY = "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
LOGIN_POLICY = (
	"default-src 'self'; script-src 'self'; frame-ancestors 'none'; "
	"object-src 'none'; base-uri 'self'; form-action 'self'"
)
EXPECTED_HEADERS = {
	"X-Content-Type-Options": "nosniff",
	"Referrer-Policy": "strict-origin-when-cross-origin",
}


class TestShellResponseHeaders(ShellHTTPFixture):
	def assert_security_headers(self, headers, policy=BASE_POLICY, frame_options="SAMEORIGIN"):
		for name, expected in {**EXPECTED_HEADERS, CSP: policy, "X-Frame-Options": frame_options}.items():
			with self.subTest(header=name):
				actual = [header_value for key, header_value in headers if key.lower() == name.lower()]
				self.assertEqual(actual, [expected])

	def test_headers_on_success_and_not_modified(self):
		status, headers, _unused_body = self.request(BOOTSTRAP, self.reader_sid, response_header_type=list)
		self.assertEqual(status, 200)
		self.assert_security_headers(headers)
		status, headers, body = self.request(
			BOOTSTRAP,
			self.reader_sid,
			headers={"If-None-Match": dict(headers)["ETag"]},
			response_header_type=list,
		)
		self.assertEqual((status, body), (304, b""))
		self.assert_security_headers(headers)

	def test_headers_on_guest_page_redirect_and_denial(self):
		for path, expected in (("/login", 200), ("/panel", 302), (BOOTSTRAP, 403)):
			with self.subTest(path=path):
				status, headers, _unused_body = self.request(path, response_header_type=list)
				self.assertEqual(status, expected)
				if path in ("/panel", "/login"):
					self.assert_security_headers(headers, LOGIN_POLICY, "DENY")
				else:
					self.assert_security_headers(headers)

	def test_login_aliases_have_strict_headers(self):
		for path in ("/login.html", "//login", "/login%20"):
			with self.subTest(path=path):
				status, headers, body = self.request(path, response_header_type=list)
				self.assertEqual(status, 200)
				self.assertIn(b'data-page="platform-core-login"', body)
				self.assert_security_headers(headers, LOGIN_POLICY, "DENY")

	def test_login_home_page_has_strict_headers(self):
		settings = "Website Settings"
		home_page = frappe.db.get_single_value(settings, "home_page")
		try:
			frappe.db.set_single_value(settings, "home_page", "login")
			frappe.db.commit()
			frappe.cache.delete_value("home_page")
			for path in ("/", "/index"):
				with self.subTest(path=path):
					status, headers, body = self.request(path, response_header_type=list)
					self.assertEqual(status, 200)
					self.assertIn(b'data-page="platform-core-login"', body)
					self.assert_security_headers(headers, LOGIN_POLICY, "DENY")
		finally:
			frappe.db.set_single_value(settings, "home_page", home_page)
			frappe.db.commit()
			frappe.cache.delete_value("home_page")

	def test_authenticated_login_redirect_has_strict_headers(self):
		status, headers, _unused_body = self.request(
			"/login?redirect-to=/panel", self.reader_sid, response_header_type=list
		)
		self.assert_security_headers(headers, LOGIN_POLICY, "DENY")
		self.assertEqual(status, 302)
		self.assertEqual(dict(headers)["Location"], "/panel")

	def test_desk_and_panel_keep_their_script_delivery(self):
		for path, sid, policy, frame_options, prepared_body in (
			("/desk", self.desk_sid, BASE_POLICY, "SAMEORIGIN", b"frappe.boot ="),
			("/panel", self.reader_sid, LOGIN_POLICY, "DENY", b'name="csrf-token"'),
		):
			with self.subTest(path=path):
				status, headers, body = self.request(path, sid, response_header_type=list)
				self.assertEqual(status, 200)
				self.assert_security_headers(headers, policy, frame_options)
				self.assertIn(prepared_body, body)

	def test_login_session_cookie_is_http_only(self):
		status, headers, _unused_body = self.request(
			"/api/method/login",
			method="POST",
			data={"usr": DESK, "pwd": self.password},
			response_header_type=list,
		)
		self.assertEqual(status, 200)
		cookies = SimpleCookie()
		for name, header_value in headers:
			if name.lower() == "set-cookie":
				cookies.load(header_value)
		self.assertTrue(cookies["sid"]["httponly"])
		for name in ("user_id", "full_name"):
			self.assertFalse(cookies[name]["httponly"])
