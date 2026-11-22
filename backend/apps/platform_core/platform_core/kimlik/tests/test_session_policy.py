"""Session idle timeout (O-25) and the AI write closure of the identity link (O-28).

Expected behaviour comes from PROJE-KAYDI.md O-25 and O-28 (D-1):
- the Frappe cookie session ends after 1 hour without activity, for employees and customers,
- an employee who was idle for 1 hour authenticates again; the open Keycloak cookie does not skip it,
- a session that ended answers 401 `SessionExpired`, not 403 (SZ-8),
- the identity link DocType is listed in the `ai_write_closed_doctypes` hook.
"""

import time
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup, session_policy
from platform_core.kimlik.tests import helpers as h

EMPLOYEE = "calisan.ornek@example.test"


def _query(location: str) -> dict:
	return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


class TestSessionPolicy(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		# Frappe derives `user_type` from roles: a desk role makes the user an employee (System User).
		role = h.ensure_role("Kimlik Test Employee", 1)
		h.ensure_user(EMPLOYEE, user_type="System User", roles=[role])
		frappe.get_doc("User", EMPLOYEE).add_roles(role)
		previous = frappe.db.get_single_value("System Settings", "session_expiry")
		cls.addClassCleanup(frappe.db.set_single_value, "System Settings", "session_expiry", previous)
		# The site runs with the policy, like after migrate.
		session_policy.apply()
		h.refresh()
		cls.patcher = h.jwks_patch()
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	@classmethod
	def tearDownClass(cls):
		h.clear_links(EMPLOYEE)
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links(EMPLOYEE)
		h.reset_rate_limits()
		self.client = h.new_client()

	# --- O-25: Frappe idle timeout -------------------------------------------------------------

	def test_install_and_migrate_hooks_apply_the_idle_timeout(self):
		self.assertIn("platform_core.kimlik.session_policy.apply", frappe.get_hooks("after_install"))
		self.assertIn("platform_core.kimlik.session_policy.apply", frappe.get_hooks("after_migrate"))
		previous = frappe.db.get_single_value("System Settings", "session_expiry")
		self.addCleanup(frappe.db.set_single_value, "System Settings", "session_expiry", previous)
		frappe.db.set_single_value("System Settings", "session_expiry", "170:00")
		session_policy.apply()
		self.assertEqual(frappe.db.get_single_value("System Settings", "session_expiry"), "01:00:00")

	def test_keycloak_session_carries_one_hour_idle_timeout(self):
		# The session record keeps its own expiry. A later System Settings change does not extend it.
		previous = frappe.db.get_single_value("System Settings", "session_expiry")
		self.addCleanup(frappe.db.set_single_value, "System Settings", "session_expiry", previous)
		frappe.db.set_single_value("System Settings", "session_expiry", "170:00")
		frappe.clear_cache()
		response = h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(response.status_code, 302, response.data[:300])
		sid = self.client.get_cookie("sid").value
		data = frappe.cache.hget("session", sid)
		self.assertEqual(data["data"]["session_expiry"], "01:00:00")

	def test_idle_session_answers_401_session_expired(self):
		response = h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(response.status_code, 302, response.data[:300])
		sid = self.client.get_cookie("sid").value
		self._age_session(sid, seconds=3601)
		answer = h.request(
			self.client.post, "/api/method/platform_core.api.auth.logout", headers=h.csrf_headers(self.client)
		)
		self.assertEqual(answer.status_code, 401, answer.data[:300])
		self.assertEqual(answer.json.get("exc_type"), "SessionExpired")
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_active_session_within_the_hour_stays_open(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		sid = self.client.get_cookie("sid").value
		self._age_session(sid, seconds=3000)
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	# --- O-25: an idle employee authenticates again ---------------------------------------------

	def test_employee_with_old_authentication_is_sent_back_to_keycloak(self):
		_started, query = h.start_login(self.client, "/app")
		token = h.id_token(query, h.userinfo("sub-calisan", EMPLOYEE), auth_time=int(time.time()) - 7200)
		response = h.finish_login(self.client, query, token)
		self.assertEqual(response.status_code, 302, response.data[:300])
		again = _query(response.headers["Location"])
		self.assertTrue(
			response.headers["Location"].startswith(h.ISSUER + "/protocol/openid-connect/auth?"),
			response.headers["Location"],
		)
		self.assertEqual(again.get("prompt"), "login")
		self.assertNotEqual(again["state"], query["state"])
		self.assertEqual(h.logged_user(self.client), "Guest")
		# The new attempt keeps the redirect target and signs in with a fresh authentication.
		fresh = h.id_token(again, h.userinfo("sub-calisan", EMPLOYEE))
		done = h.finish_login(self.client, again, fresh)
		self.assertEqual(done.status_code, 302, done.data[:300])
		self.assertTrue(done.headers["Location"].endswith("/app"))
		self.assertEqual(h.logged_user(self.client), EMPLOYEE)

	def test_employee_without_auth_time_is_sent_back_to_keycloak(self):
		_started, query = h.start_login(self.client)
		token = h.id_token(query, h.userinfo("sub-calisan", EMPLOYEE), auth_time=None)
		response = h.finish_login(self.client, query, token)
		self.assertEqual(response.status_code, 302, response.data[:300])
		self.assertEqual(_query(response.headers["Location"]).get("prompt"), "login")
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_stale_authentication_after_forced_login_is_refused(self):
		_started, query = h.start_login(self.client)
		stale = int(time.time()) - 7200
		first = h.finish_login(
			self.client, query, h.id_token(query, h.userinfo("sub-calisan", EMPLOYEE), auth_time=stale)
		)
		again = _query(first.headers["Location"])
		second = h.finish_login(
			self.client, again, h.id_token(again, h.userinfo("sub-calisan", EMPLOYEE), auth_time=stale)
		)
		self.assertEqual(second.status_code, 403, second.data[:300])
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_employee_with_recent_authentication_signs_in(self):
		_started, query = h.start_login(self.client)
		token = h.id_token(query, h.userinfo("sub-calisan", EMPLOYEE), auth_time=int(time.time()) - 600)
		response = h.finish_login(self.client, query, token)
		self.assertEqual(response.status_code, 302, response.data[:300])
		self.assertNotIn("prompt=login", response.headers["Location"])
		self.assertEqual(h.logged_user(self.client), EMPLOYEE)

	def test_customer_with_old_authentication_signs_in(self):
		# Customers keep the Keycloak 7 day idle window (O-25 table). Only the Frappe cookie is 1 hour.
		_started, query = h.start_login(self.client)
		token = h.id_token(query, h.userinfo("sub-ayse", h.AYSE), auth_time=int(time.time()) - 7200)
		response = h.finish_login(self.client, query, token)
		self.assertEqual(response.status_code, 302, response.data[:300])
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	# --- O-28: AI write closure -----------------------------------------------------------------

	def test_identity_link_is_closed_to_ai_writes(self):
		closed = frappe.get_hooks("ai_write_closed_doctypes")
		self.assertIn("Platform Identity Link", closed)
		for doctype in closed:
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

	# --- helpers ---------------------------------------------------------------------------------

	def _age_session(self, sid: str, seconds: int) -> None:
		"""Moves the session's last activity back, in the cache and in the database."""
		from frappe.utils import add_to_date, now_datetime

		then = add_to_date(now_datetime(), seconds=-seconds, as_string=True, as_datetime=True)
		data = frappe.cache.hget("session", sid)
		data["data"]["last_updated"] = then
		frappe.cache.hset("session", sid, data)
		frappe.db.sql("update tabSessions set lastupdate=%s where sid=%s", (then, sid))
		frappe.db.commit()
