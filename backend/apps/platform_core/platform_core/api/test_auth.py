"""Negative access checks through Frappe's HTTP dispatch."""

import secrets
from unittest.mock import patch

from frappe.tests.test_api import FrappeAPITestCase
from frappe.utils.password import update_password

from platform_core.identity import provider_setup
from platform_core.identity.tests import helpers as h

PREFIX = "/api/method/platform_core.api.auth."
TOKEN_PATH = PREFIX + "get_csrf_token"
LOGOUT_PATH = PREFIX + "logout"


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
		h.reset_rate_limits()

	def login(self, user, subject):
		client = h.new_client()
		with h.jwks_patch():
			self.assertEqual(h.login_with_keycloak(client, h.userinfo(subject, user)).status_code, 302)
		self.assertEqual(h.logged_user(client), user)
		return client

	def password_login(self, user):
		"""Opens a session through Frappe's own login. Such a session has no CSRF token yet (frappe/sessions.py:255)."""
		password = secrets.token_urlsafe(24)
		update_password(user, password)
		h.refresh()
		client = h.new_client()
		response = h.request(client.post, "/api/method/login", data={"usr": user, "pwd": password})
		self.assertEqual(response.status_code, 200, response.data[:200])
		self.assertEqual(h.logged_user(client), user)
		return client

	def csrf_token(self, client) -> str:
		"""Calls the endpoint as production does. While `frappe.in_test` is set, Frappe skips the session
		write that stores a new token (frappe/sessions.py:211); production never sets it."""
		with patch("frappe.in_test", False):
			response = h.request(client.get, TOKEN_PATH)
		self.assertEqual(response.status_code, 200, response.data[:200])
		return response.json["message"]["csrf_token"]

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

	# --- get_csrf_token: the separate frontend reads the token from this endpoint, not from the page ---

	def test_get_csrf_token_guest_denied(self):
		response = h.request(h.new_client().get, TOKEN_PATH)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "PermissionError")
		self.assertNotIn("message", response.json)

	def test_get_csrf_token_foreign_data_denied(self):
		"""A token belongs to one session. Another session's write does not pass with it."""
		caller = self.login(h.AYSE, "fixture-first")
		other = self.login(h.MEHMET, "fixture-second")
		token = self.csrf_token(caller)
		self.assertNotEqual(token, h.csrf_token_of(other))
		response = h.request(other.post, LOGOUT_PATH, headers={"X-Frappe-CSRF-Token": token})
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json["exc_type"], "CSRFTokenError")
		self.assertEqual(h.logged_user(other), h.MEHMET)

	def test_get_csrf_token_returns_the_session_token(self):
		client = self.login(h.AYSE, "fixture-first")
		response = h.request(client.get, TOKEN_PATH)
		self.assertEqual(response.status_code, 200, response.data[:200])
		token = h.csrf_token_of(client)
		self.assertTrue(token)
		self.assertEqual(response.json["message"], {"csrf_token": token})

	def test_get_csrf_token_creates_a_missing_token(self):
		client = self.password_login(h.AYSE)
		self.assertIsNone(h.csrf_token_of(client))
		token = self.csrf_token(client)
		self.assertTrue(token)
		self.assertEqual(h.csrf_token_of(client), token)
		self.assertEqual(self.csrf_token(client), token)

	def test_get_csrf_token_post_denied(self):
		client = self.login(h.AYSE, "fixture-first")
		response = h.request(client.post, TOKEN_PATH, headers=h.csrf_headers(client))
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "PermissionError")

	def test_get_csrf_token_is_not_cached(self):
		client = self.login(h.AYSE, "fixture-first")
		response = h.request(client.get, TOKEN_PATH)
		self.assertEqual(response.status_code, 200)
		directives = {part.strip() for part in response.headers.get("Cache-Control", "").split(",")}
		self.assertIn("no-store", directives)
		self.assertNotIn("ETag", response.headers)
		self.assertNotIn("Last-Modified", response.headers)
		conditional = h.request(client.get, TOKEN_PATH, headers={"If-None-Match": '"stale"'})
		self.assertEqual(conditional.status_code, 200)
		self.assertEqual(conditional.json["message"]["csrf_token"], response.json["message"]["csrf_token"])

	def test_get_csrf_token_has_no_cors_grant(self):
		client = self.login(h.AYSE, "fixture-first")
		response = h.request(client.get, TOKEN_PATH, headers={"Origin": "https://other.example.test"})
		self.assertEqual(response.status_code, 200)
		self.assertNotIn("Access-Control-Allow-Origin", response.headers)
		self.assertNotIn("Access-Control-Allow-Credentials", response.headers)

	def test_returned_token_passes_the_csrf_check(self):
		client = self.password_login(h.AYSE)
		token = self.csrf_token(client)
		wrong = h.request(client.post, LOGOUT_PATH, headers={"X-Frappe-CSRF-Token": secrets.token_hex(16)})
		self.assertEqual(wrong.status_code, 400)
		self.assertEqual(wrong.json["exc_type"], "CSRFTokenError")
		missing = h.request(client.post, LOGOUT_PATH)
		self.assertEqual(missing.status_code, 400)
		self.assertEqual(missing.json["exc_type"], "CSRFTokenError")
		self.assertEqual(h.logged_user(client), h.AYSE)
		right = h.request(client.post, LOGOUT_PATH, headers={"X-Frappe-CSRF-Token": token})
		self.assertEqual(right.status_code, 200, right.data[:200])
		self.assertEqual(h.logged_user(client), "Guest")

	def test_get_csrf_token_rate_limited(self):
		client = self.login(h.AYSE, "fixture-first")
		h.reset_rate_limits()
		for _call in range(30):
			self.assertEqual(h.request(client.get, TOKEN_PATH).status_code, 200)
		response = h.request(client.get, TOKEN_PATH)
		self.assertEqual(response.status_code, 429)
		self.assertEqual(response.json["exc_type"], "RateLimitExceededError")
