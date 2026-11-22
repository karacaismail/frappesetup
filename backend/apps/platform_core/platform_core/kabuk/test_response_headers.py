"""Check the security headers on actual Frappe HTTP responses."""

from platform_core.tests.shell_http_fixture import ShellHTTPFixture

BOOTSTRAP = "/api/method/platform_core.api.shell.get_bootstrap"
EXPECTED_HEADERS = {
	"X-Content-Type-Options": "nosniff",
	"Referrer-Policy": "strict-origin-when-cross-origin",
	"X-Frame-Options": "SAMEORIGIN",
}


class TestShellResponseHeaders(ShellHTTPFixture):
	def assert_security_headers(self, headers):
		for name, expected in EXPECTED_HEADERS.items():
			with self.subTest(header=name):
				actual = [value for key, value in headers if key.lower() == name.lower()]
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
		status, headers, _unused_body = self.request("/", response_header_type=list)
		self.assertIn(status, (200, 302))
		self.assert_security_headers(headers)
		for path, expected in (("/login", 200), ("/panel", 302), (BOOTSTRAP, 403)):
			with self.subTest(path=path):
				status, headers, _unused_body = self.request(path, response_header_type=list)
				self.assertEqual(status, expected)
				self.assert_security_headers(headers)
				if path == "/panel":
					self.assertEqual(
						dict(headers)["Content-Security-Policy"], "default-src 'self'; frame-ancestors 'none'"
					)
