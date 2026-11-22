import json
from html.parser import HTMLParser

import frappe

from platform_core.tests.shell_http_fixture import DOCTYPE, READER, ShellHTTPFixture


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
		self.assertEqual(headers["Content-Security-Policy"], "default-src 'self'; frame-ancestors 'none'")
		self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
		self.assertIsNone(PanelMetadata(body).token)

	def test_token_is_stable_within_session_and_distinct_across_sessions(self):
		def panel_token(sid):
			status, headers, body = self.request("/panel", sid)
			self.assertEqual(status, 200)
			self.assertIn("private", headers["Cache-Control"])
			self.assertIn("no-store", headers["Cache-Control"])
			self.assertEqual(headers["Vary"], "Cookie")
			self.assertEqual(headers["Content-Security-Policy"], "default-src 'self'; frame-ancestors 'none'")
			self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
			token = PanelMetadata(body).token
			self.assertTrue(token)
			return token

		first = panel_token(self.reader_sid)
		self.assertEqual(first, panel_token(self.reader_sid))
		other_sid = self.login(READER)
		self.assertNotEqual(self.reader_sid, other_sid)
		other = panel_token(other_sid)
		self.assertNotEqual(first, other)
		for token, expected in ((None, 400), (other, 400), (first, 200)):
			headers = {"X-Frappe-CSRF-Token": token} if token else {}
			status, _, body = self.request(
				"/api/method/frappe.client.insert",
				self.reader_sid,
				method="POST",
				data={"doc": json.dumps({"doctype": DOCTYPE, "title": "Shell CSRF test"})},
				headers=headers,
			)
			self.assertEqual(status, expected)
			if expected == 400:
				self.assertEqual(json.loads(body)["exc_type"], "CSRFTokenError")
			else:
				frappe.delete_doc(DOCTYPE, json.loads(body)["message"]["name"])
				frappe.db.commit()

	def test_panel_uses_the_requested_language(self):
		for language, title in (("en", "Admin panel"), ("tr", "Yönetim paneli")):
			with self.subTest(language=language):
				status, _, body = self.request(f"/panel?_lang={language}", self.reader_sid)
				self.assertEqual(status, 200)
				self.assertIn(f'<html lang="{language}">', body.decode("utf-8"))
				self.assertIn(f"<title>{title}</title>", body.decode("utf-8"))
