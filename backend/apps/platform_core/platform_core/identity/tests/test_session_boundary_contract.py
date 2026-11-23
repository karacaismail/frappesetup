"""G-43: exact O-25 idle boundary through authenticated HTTP requests.

The one-hour product decision supersedes the older twelve-hour site text.
Keycloak exchange is faked; Frappe sessions, Redis and request hooks are real.
"""

import time
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import provider_setup, session_policy
from platform_core.identity.tests import helpers as h


class TestSessionBoundaryContract(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = h.SiteSettings()
		settings.__enter__()
		cls.addClassCleanup(settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		verification = h.jwks_patch()
		verification.start()
		cls.addClassCleanup(verification.stop)

	def setUp(self):
		super().setUp()
		h.clear_links()
		h.reset_rate_limits()
		self.addCleanup(h.clear_links)
		self.client = h.new_client()
		response = h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(response.status_code, 302)
		self.sid = self.client.get_cookie("sid").value
		self.activity_key = session_policy._session_key(self.sid)
		h.refresh()
		self.assertEqual(frappe.db.count("Sessions", {"sid": self.sid}), 1)

	def request_at_idle_age(self, seconds, *, authorization=False):
		now = int(time.time())
		frappe.cache.set_value(self.activity_key, now - seconds, expires_in_sec=3600)
		headers = {"Authorization": "Bearer unrelated-token"} if authorization else {}
		# Only wall-clock time is frozen. The real hook and session deletion must execute.
		with patch.object(session_policy.time, "time", return_value=now):
			return h.request(self.client.get, "/api/method/frappe.auth.get_logged_user", headers=headers)

	def test_one_second_before_idle_limit_keeps_the_session(self):
		response = self.request_at_idle_age(3599)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"], h.AYSE)
		h.refresh()
		self.assertEqual(frappe.db.count("Sessions", {"sid": self.sid}), 1)

	def test_exact_idle_limit_ends_the_session(self):
		response = self.request_at_idle_age(3600)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json["exc_type"], "SessionExpired")
		h.refresh()
		self.assertEqual(frappe.db.count("Sessions", {"sid": self.sid}), 0)

	def test_authorization_header_cannot_extend_an_expired_cookie_session(self):
		response = self.request_at_idle_age(3600, authorization=True)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json["exc_type"], "SessionExpired")
		h.refresh()
		self.assertEqual(frappe.db.count("Sessions", {"sid": self.sid}), 0)
