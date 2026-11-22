"""AU-19 (Keycloak-only sign-in) and A-7 (portal pages closed) tests."""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h


class TestKeycloakOnly(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()

	@classmethod
	def tearDownClass(cls):
		h.clear_links()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links()

	def password_login(self):
		return h.request(
			h.new_client().post,
			"/api/method/login",
			data={"usr": "Administrator", "pwd": frappe.conf.admin_password or "admin"},
		)

	def test_password_login_works_while_gate_is_off(self):
		response = self.password_login()
		self.assertEqual(response.status_code, 200, response.data[:200])

	def test_gate_on_rejects_password_and_email_link_but_keycloak_works(self):
		with h.SiteSettings({"kimlik_yalniz_keycloak": 1}):
			password = self.password_login()
			self.assertEqual(password.status_code, 401, password.data[:200])

			with self.change_settings("System Settings", login_with_email_link=1, commit=True):
				link = h.request(
					h.new_client().post,
					"/api/method/frappe.www.login.send_login_link",
					data={"email": h.AYSE},
				)
				self.assertEqual(link.status_code, 403)
				key = h.request(
					h.new_client().get,
					"/api/method/frappe.www.login.login_via_key",
					query_string={"key": "x"},
				)
				self.assertEqual(key.status_code, 403)

			client = h.new_client()
			response = h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
			self.assertEqual(response.status_code, 302)
			self.assertEqual(h.logged_user(client), h.AYSE)

	def test_portal_pages_are_closed_to_end_users(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
		for path in ("/me", "/update-profile", "/update-password", "/third_party_apps", "/portal"):
			response = h.request(client.get, path, follow_redirects=True)
			self.assertEqual(response.status_code, 403, f"{path}: {response.status_code}")

	def test_portal_page_stays_open_to_administrator(self):
		admin = h.new_client()
		admin.set_cookie("sid", self.sid)
		response = h.request(admin.get, "/me", follow_redirects=True)
		self.assertEqual(response.status_code, 200)
