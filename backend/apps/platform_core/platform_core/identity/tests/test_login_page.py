"""The tenant `/login` page and the GET sign-in starter `platform_core.api.auth.start_login`.

Expected behaviour (orchestrator decision after the integration preview, docs/sozlesmeler.md section 5):
- `start_login` creates the browser cookie and the state record and answers 302 to Keycloak,
- `redirect_to` may only be a same-origin relative path,
- with `identity_keycloak_only` on, `/login` redirects to the sign-in starter,
- with the gate off the page also offers a plain password form against `/api/method/login`,
- the button label comes from the brand setting, English source with Turkish translation.
"""

from urllib.parse import parse_qs, urlparse

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import provider_setup
from platform_core.identity.tests import helpers as h

START = "/api/method/platform_core.api.auth.start_login"
AUTHORIZE = "http://identity.localhost:8660/realms/platform/protocol/openid-connect/auth?"


class TestLoginPage(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.patcher = h.jwks_patch()
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	@classmethod
	def tearDownClass(cls):
		h.clear_links()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links()
		self.client = h.new_client()

	def test_start_login_sets_cookie_and_redirects_to_keycloak(self):
		response = h.request(self.client.get, START, query_string={"redirect_to": "/panel"})
		self.assertEqual(response.status_code, 302, response.data[:300])
		location = response.headers["Location"]
		self.assertTrue(location.startswith(AUTHORIZE), location)
		query = {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}
		self.assertEqual(query["code_challenge_method"], "S256")
		self.assertEqual(query["redirect_uri"], "http://tenant1.localhost:8661" + h.CALLBACK)
		cookies = response.headers.getlist("Set-Cookie")
		self.assertTrue(any(c.startswith(f"{h.LOGIN_COOKIE}=") and "HttpOnly" in c for c in cookies), cookies)
		# The started attempt can be finished by the same browser.
		finished = h.finish_login(self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE)))
		self.assertEqual(finished.status_code, 302, finished.data[:300])
		self.assertTrue(finished.headers["Location"].endswith("/panel"))
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	def test_start_login_rejects_external_redirect_and_post(self):
		for target in ("https://evil.example/", "//evil.example/panel", "panel"):
			response = h.request(self.client.get, START, query_string={"redirect_to": target})
			self.assertEqual(response.status_code, 400, target)
			self.assertIn(b"<!DOCTYPE html>", response.data[:100])
		response = h.request(self.client.post, START)
		self.assertEqual(response.status_code, 403)

	def test_start_login_without_settings_is_503(self):
		with h.SiteSettings({"keycloak_client_secret": ""}):
			response = h.request(self.client.get, START)
		self.assertEqual(response.status_code, 503)

	def test_login_page_with_gate_on_redirects_without_rendering_a_password_form(self):
		with h.SiteSettings({"identity_keycloak_only": 1}):
			for path, destination in (
				("/desk?tab=1", f"{START}?redirect_to=%2Fdesk%3Ftab%3D1"),
				("//external.example/desk", START),
			):
				with self.subTest(path=path):
					response = h.request(self.client.get, "/login", query_string={"redirect-to": path})
					self.assertEqual(response.status_code, 302)
					self.assertEqual(response.headers["Location"], destination)
					self.assertNotIn(b'type="password"', response.data)

	def test_login_page_with_gate_off_adds_a_plain_password_form(self):
		response = h.request(self.client.get, "/login", headers={"Accept-Language": "en"})
		self.assertEqual(response.status_code, 200)
		html = response.data.decode()
		self.assertIn("Sign in with Atonota", html)
		self.assertIn(f'href="{START}"', html)
		self.assertIn('name="pwd"', html)
		self.assertIn('name="usr"', html)
		self.assertIn('data-login-endpoint="/api/method/login"', html)

	def test_login_page_drops_unsafe_redirect(self):
		response = h.request(self.client.get, "/login", query_string={"redirect-to": "https://evil.example/"})
		html = response.data.decode()
		self.assertIn(f'href="{START}"', html)
		self.assertNotIn("evil.example", html)

	def test_login_page_redirects_signed_in_users(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		# Frappe answers a website redirect with 301 (frappe.Redirect).
		response = h.request(self.client.get, "/login", query_string={"redirect-to": "/panel?tab=1"})
		self.assertIn(response.status_code, (301, 302))
		self.assertTrue(response.headers["Location"].endswith("/panel?tab=1"))
		response = h.request(self.client.get, "/login")
		self.assertIn(response.status_code, (301, 302))
		self.assertTrue(response.headers["Location"].endswith("/panel"))

	def test_login_page_without_settings_explains_instead_of_crashing(self):
		with h.SiteSettings({"identity_brand_name": ""}):
			response = h.request(self.client.get, "/login", headers={"Accept-Language": "en"})
		self.assertEqual(response.status_code, 200)
		html = response.data.decode()
		self.assertIn("not configured", html)
		self.assertNotIn(START, html)

	def test_assets_are_served_from_the_app(self):
		for path in (
			"/assets/platform_core/identity/login.css",
			"/assets/platform_core/identity/fonts/outfit-latin-wght-normal.woff2",
		):
			exists = frappe.get_app_path("platform_core", "public", path.split("/assets/platform_core/")[1])
			self.assertTrue(frappe.utils.os.path.exists(exists), path)
