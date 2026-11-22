import csv
from html.parser import HTMLParser
from pathlib import Path

from platform_core.shell.http_fixture import ShellHTTPFixture


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

	def test_panel_uses_the_requested_language(self):
		source = "Management panel"
		catalog = Path(__file__).resolve().parents[1] / "translations" / "tr.csv"
		with catalog.open(encoding="utf-8", newline="") as stream:
			translation = dict(csv.reader(stream))[source]
		self.assertNotEqual(translation, source)
		for language, title in (("en", source), ("tr", translation)):
			with self.subTest(language=language):
				status, _, body = self.request(f"/panel?_lang={language}", self.reader_sid)
				self.assertEqual(status, 200)
				self.assertIn(f'<html lang="{language}">', body.decode("utf-8"))
				self.assertIn(f"<title>{title}</title>", body.decode("utf-8"))
