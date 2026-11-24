"""Negative access checks through Frappe's HTTP dispatch."""

import copy
import secrets
from unittest.mock import patch

import frappe
import redis
from frappe.tests.test_api import FrappeAPITestCase
from frappe.utils import add_days, now_datetime
from frappe.utils.password import update_password

from platform_core.identity import login_accounts, provider_setup, session_policy
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

	# --- AtonotA Login reads (AJA-459): api/test_login_reads.py covers them in full ---

	def _refusing_identity_sync(self):
		"""No request may reach identity-sync in the refusal tests below."""
		calls = []
		transport = patch.object(login_accounts, "_send", lambda *args: calls.append(args) or (200, {}))
		transport.start()
		self.addCleanup(transport.stop)
		return calls

	def test_list_login_providers_guest_denied(self):
		calls = self._refusing_identity_sync()
		response = h.request(h.new_client().get, PREFIX + "list_login_providers")
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "PermissionError")
		self.assertEqual(calls, [])

	def test_list_login_providers_foreign_data_denied(self):
		"""The platform list takes no person. Another user's subject is refused."""
		calls = self._refusing_identity_sync()
		caller = self.login(h.AYSE, "fixture-first")
		response = h.request(
			caller.get, PREFIX + "list_login_providers", query_string={"subject": "fixture-second"}
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json["exc_type"], "InvalidInput")
		self.assertEqual(calls, [])

	def test_list_linked_accounts_guest_denied(self):
		calls = self._refusing_identity_sync()
		response = h.request(h.new_client().get, PREFIX + "list_linked_accounts")
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "PermissionError")
		self.assertEqual(calls, [])

	def test_list_linked_accounts_foreign_data_denied(self):
		"""Ayşe cannot read Mehmet's linked accounts by naming him."""
		calls = self._refusing_identity_sync()
		self.login(h.MEHMET, "fixture-second")
		caller = self.login(h.AYSE, "fixture-first")
		for name, value in (("subject", "fixture-second"), ("user", h.MEHMET)):
			with self.subTest(name=name):
				response = h.request(caller.get, PREFIX + "list_linked_accounts", query_string={name: value})
				self.assertEqual(response.status_code, 400)
				self.assertEqual(response.json["exc_type"], "InvalidInput")
		self.assertEqual(calls, [])

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
		self.assertIn("private", directives)
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

	def test_get_csrf_token_expired_session(self):
		"""Frappe opens an expired session as Guest and marks `session_expired` (frappe/sessions.py:346).
		A whitelisted method that guests may not call then raises `SessionExpired` (frappe/__init__.py:483)."""
		for case in ("frappe_expiry", "idle_timeout"):
			with self.subTest(case=case):
				client = self.login(h.AYSE, "fixture-first")
				sid = client.get_cookie("sid").value
				if case == "frappe_expiry":
					sessions = frappe.qb.DocType("Sessions")
					frappe.qb.update(sessions).set(sessions.lastupdate, add_days(now_datetime(), -30)).where(
						sessions.sid == sid
					).run()
					frappe.cache.hdel("session", sid)
					h.refresh()
					response = h.request(client.get, TOKEN_PATH)
				else:
					with patch.object(session_policy, "IDLE_SECONDS", 0):
						response = h.request(client.get, TOKEN_PATH)
				self.assertEqual(response.status_code, 401, response.data[:200])
				self.assertEqual(response.json["exc_type"], "SessionExpired")
				self.assertNotIn("message", response.json)
				self.assertEqual(h.logged_user(client), "Guest")

	def test_get_csrf_token_waiting_request_reads_the_stored_token(self):
		"""Two tabs share one session without a token and call the endpoint at the same time.

		The test client runs one request at a time, so the race is staged inside the lock: while the
		second tab waits for the lock, the first tab stores its token in the shared session record.
		The waiting tab must return that token and must not create a second one."""
		client = self.password_login(h.AYSE)
		sid = client.get_cookie("sid").value
		first_tab = secrets.token_hex(16)
		order = []
		real_lock = redis.Redis.lock

		def store_as_first_tab():
			# Another worker process writes Redis only. This request keeps its stale copy without a token.
			stale = copy.deepcopy(frappe.cache.hget("session", sid))
			self.assertFalse(stale["data"].get("csrf_token"))
			stored = copy.deepcopy(stale)
			stored["data"]["csrf_token"] = first_tab
			frappe.cache.hset("session", sid, stored)
			frappe.local.cache[frappe.cache.make_key("session")][sid] = stale
			order.append("first tab stored")

		def lock(cache, name, *args, **kwargs):
			held = real_lock(cache, name, *args, **kwargs)
			if "csrf_token" not in str(name):
				return held
			self.assertNotIn(sid, str(name))
			acquire = held.acquire

			def acquire_after_first_tab(*acquire_args, **acquire_kwargs):
				order.append("waiting")
				store_as_first_tab()
				return acquire(*acquire_args, **acquire_kwargs)

			held.acquire = acquire_after_first_tab
			return held

		generate = frappe.sessions.generate_csrf_token
		with (
			patch.object(type(frappe.cache), "lock", lock),
			patch.object(frappe.sessions, "generate_csrf_token", wraps=generate) as generated,
		):
			token = self.csrf_token(client)
		self.assertEqual(order, ["waiting", "first tab stored"])
		self.assertEqual(token, first_tab)
		generated.assert_not_called()
		self.assertEqual(self.csrf_token(client), first_tab)
