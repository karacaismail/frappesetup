from html.parser import HTMLParser

from platform_core.kabuk.http_fixture import ShellHTTPFixture


class PanelMetadata(HTMLParser):
	def __init__(self, body: bytes):
		super().__init__()
		self.token = None
		self.feed(body.decode("utf-8"))

	def handle_starttag(self, tag, attrs):
		attributes = dict(attrs)
		if tag == "meta" and attributes.get("name") == "csrf-token":
			self.token = attributes.get("content")


class TestPanelHTTP(ShellHTTPFixture):
	def test_guest_redirects_to_login_without_token(self):
		status, headers, body = self.request("/panel")
		self.assertEqual(status, 302)
		self.assertEqual(headers["Location"], "/login?redirect-to=/panel")
		self.assertIn("no-store", headers["Cache-Control"])
		self.assertIsNone(PanelMetadata(body).token)

	def test_token_is_stable_within_session_and_distinct_across_sessions(self):
		def panel_token(sid):
			status, headers, body = self.request("/panel", sid)
			self.assertEqual(status, 200)
			self.assertIn("private", headers["Cache-Control"])
			self.assertIn("no-store", headers["Cache-Control"])
			token = PanelMetadata(body).token
			self.assertTrue(token)
			return token

		first = panel_token(self.reader_sid)
		self.assertEqual(first, panel_token(self.reader_sid))
		self.assertNotEqual(first, panel_token(self.privileged_sid))
