"""Negative access checks through Frappe's HTTP dispatch."""

from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import provider_setup
from platform_core.identity.tests import helpers as h

PREFIX = "/api/method/platform_core.api.auth."


class TestAuthEndpointAccess(FrappeAPITestCase):
	def setUp(self):
		super().setUp()
		settings = h.SiteSettings()
		settings.__enter__()
		self.addCleanup(settings.__exit__, None, None, None)
		h.clear_links()
		self.addCleanup(h.clear_links)
		provider_setup.ensure_social_login_key()
		for user in (h.AYSE, h.MEHMET):
			h.ensure_user(user)
		h.refresh()

	def login(self, user, subject):
		client = h.new_client()
		with h.jwks_patch():
			self.assertEqual(h.login_with_keycloak(client, h.userinfo(subject, user)).status_code, 302)
		self.assertEqual(h.logged_user(client), user)
		return client

	def test_get_login_url_guest_denied(self):
		response, _query = h.start_login(h.new_client(), "https://other.example.test")
		self.assertEqual(response.status_code, 400)

	def test_get_login_url_foreign_data_denied(self):
		client = self.login(h.AYSE, "fixture-first")
		response, _query = h.start_login(client, "//other.example.test", h.csrf_headers(client))
		self.assertEqual(response.status_code, 403)

	def test_start_login_guest_denied(self):
		response = h.request(
			h.new_client().get, PREFIX + "start_login", query_string={"redirect_to": "//other.example.test"}
		)
		self.assertEqual(response.status_code, 400)
		self.assertNotIn("Location", response.headers)

	def test_start_login_foreign_data_denied(self):
		client = self.login(h.AYSE, "fixture-first")
		response = h.request(
			client.get, PREFIX + "start_login", query_string={"redirect_to": "https://other.example.test"}
		)
		self.assertEqual(response.status_code, 403)
		self.assertNotIn("Location", response.headers)

	def test_keycloak_callback_guest_denied(self):
		response = h.request(
			h.new_client().get, h.CALLBACK, query_string={"code": "fixture", "state": "unknown"}
		)
		self.assertEqual(response.status_code, 400)

	def test_keycloak_callback_foreign_data_denied(self):
		first, second = h.new_client(), h.new_client()
		self.assertEqual(h.start_login(second)[0].status_code, 200)
		started, query = h.start_login(first)
		self.assertEqual(started.status_code, 200)
		response = h.finish_login(second, query, h.id_token(query, h.userinfo("fixture-first", h.AYSE)))
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(second), "Guest")

	def test_logout_guest_denied(self):
		response = h.request(h.new_client().post, PREFIX + "logout")
		self.assertEqual(response.status_code, 403)

	def test_logout_foreign_data_denied(self):
		victim = self.login(h.MEHMET, "fixture-second")
		caller = self.login(h.AYSE, "fixture-first")
		response = h.request(
			caller.post, PREFIX + "logout", json={"user": h.MEHMET}, headers=h.csrf_headers(caller)
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(h.logged_user(caller), "Guest")
		self.assertEqual(h.logged_user(victim), h.MEHMET)

	def test_setup_keycloak_login_guest_denied(self):
		response = h.request(h.new_client().post, PREFIX + "setup_keycloak_login")
		self.assertEqual(response.status_code, 403)

	def test_setup_keycloak_login_foreign_data_denied(self):
		client = self.login(h.AYSE, "fixture-first")
		response = h.request(client.post, PREFIX + "setup_keycloak_login", headers=h.csrf_headers(client))
		self.assertEqual(response.status_code, 403)
