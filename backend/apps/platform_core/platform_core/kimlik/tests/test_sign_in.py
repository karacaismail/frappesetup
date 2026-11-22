"""Sign-in with Keycloak. Requests go through the real HTTP path (D-6).

Expected behaviour comes from docs/sozlesmeler.md sections 4 and 5 and the task document (D-1):
- the right user signs in,
- an unverified e-mail cannot create the first link,
- a different `sub` cannot sign in with the same e-mail,
- a mismatching link refuses the sign-in,
- `get_login_url` creates `state` on the server and accepts only relative paths.
"""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

SID = "11111111-1111-4111-8111-111111111111"


class TestKeycloakSignIn(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		for email in h.SAMPLE_USERS:
			h.ensure_user(email)
		h.refresh()

	@classmethod
	def tearDownClass(cls):
		h.clear_links()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links()
		self.client = h.new_client()

	def test_hooks_are_wired(self):
		self.assertIn("platform_core.kimlik.sign_in.on_social_login", frappe.get_hooks("on_social_login"))
		self.assertIn(
			"platform_core.kimlik.sign_in.on_session_creation", frappe.get_hooks("on_session_creation")
		)

	def test_right_user_signs_in_and_link_is_created(self):
		response = h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID), "/panel")
		self.assertEqual(response.status_code, 302, response.data[:300])
		self.assertTrue(response.headers["Location"].endswith("/panel"))
		self.assertEqual(h.logged_user(self.client), h.AYSE)
		h.refresh()
		self.assertEqual(
			frappe.db.get_value(
				"Platform Identity Link", {"issuer": h.ISSUER, "subject": "sub-ayse"}, "user"
			),
			h.AYSE,
		)
		# The Keycloak session id is stored in the Frappe session (contract section 4).
		self.assertEqual(len(h.sessions_containing(f'"keycloak_sid":"{SID}"')), 1)

	def test_second_sign_in_uses_existing_link(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		second = h.new_client()
		response = h.login_with_keycloak(second, h.userinfo("sub-ayse", h.AYSE, email_verified=False))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(h.logged_user(second), h.AYSE)
		h.refresh()
		self.assertEqual(frappe.db.count("Platform Identity Link", {"issuer": h.ISSUER, "user": h.AYSE}), 1)

	def test_unverified_email_cannot_create_first_link(self):
		response = h.login_with_keycloak(
			self.client, h.userinfo("sub-unverified", h.UNVERIFIED, email_verified=False)
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(self.client), "Guest")
		h.refresh()
		self.assertFalse(
			frappe.db.exists("Platform Identity Link", {"issuer": h.ISSUER, "subject": "sub-unverified"})
		)

	def test_different_sub_cannot_sign_in_with_same_email(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		attacker = h.new_client()
		response = h.login_with_keycloak(attacker, h.userinfo("sub-other", h.AYSE))
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(attacker), "Guest")
		h.refresh()
		self.assertFalse(
			frappe.db.exists("Platform Identity Link", {"issuer": h.ISSUER, "subject": "sub-other"})
		)

	def test_link_owned_by_another_user_is_refused(self):
		h.make_link("sub-mehmet", h.MEHMET)
		response = h.login_with_keycloak(self.client, h.userinfo("sub-mehmet", h.AYSE))
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_unknown_email_cannot_sign_up(self):
		response = h.login_with_keycloak(self.client, h.userinfo("sub-new", "yeni.kisi@example.test"))
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(self.client), "Guest")
		h.refresh()
		self.assertFalse(frappe.db.exists("User", "yeni.kisi@example.test"))

	def test_disabled_user_cannot_sign_in(self):
		h.make_link("sub-mehmet", h.MEHMET)
		frappe.db.set_value("User", h.MEHMET, "enabled", 0)
		h.refresh()
		self.addCleanup(lambda: (frappe.db.set_value("User", h.MEHMET, "enabled", 1), h.refresh()))
		response = h.login_with_keycloak(self.client, h.userinfo("sub-mehmet", h.MEHMET))
		self.assertNotEqual(response.status_code, 302)
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_get_login_url_creates_state_on_server(self):
		response = h.request(
			self.client.post,
			"/api/method/platform_core.api.auth.get_login_url",
			json={"redirect_to": "/panel"},
			headers={"Accept-Language": "tr"},
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		result = response.json["message"]
		self.assertTrue(
			result["login_url"].startswith(
				"http://kimlik.localhost:8660/realms/platform/protocol/openid-connect/auth?"
			)
		)
		for part in (
			"state=",
			"client_id=site-kiraci1",
			"response_type=code",
			"scope=openid",
			"redirect_uri=",
		):
			self.assertIn(part, result["login_url"])
		self.assertEqual(result["brand_name"], "Atonota")
		self.assertEqual(result["label"], "Atonota ile oturum aç")
		state = result["login_url"].split("state=")[1].split("&")[0]
		self.assertEqual(frappe.cache.get_value(f"frappe_oauth_login:{state}"), "/panel")

	def test_get_login_url_rejects_external_redirect(self):
		for target in ("https://evil.example/", "//evil.example/panel", "panel"):
			response = h.request(
				self.client.post,
				"/api/method/platform_core.api.auth.get_login_url",
				json={"redirect_to": target},
			)
			self.assertEqual(response.status_code, 400, target)
			self.assertEqual(response.json.get("exc_type"), "InvalidRedirect")

	def test_get_login_url_is_post_only(self):
		# Frappe answers a wrong HTTP method with PermissionError (frappe/handler.py:110).
		response = h.request(self.client.get, "/api/method/platform_core.api.auth.get_login_url")
		self.assertEqual(response.status_code, 403)

	def test_get_login_url_returns_503_when_key_is_disabled(self):
		frappe.db.set_value("Social Login Key", "keycloak", "enable_social_login", 0)
		h.refresh()
		self.addCleanup(
			lambda: (
				frappe.db.set_value("Social Login Key", "keycloak", "enable_social_login", 1),
				h.refresh(),
			)
		)
		response = h.request(self.client.post, "/api/method/platform_core.api.auth.get_login_url", json={})
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.json.get("exc_type"), "KeycloakLoginNotConfigured")

	def test_logout_is_closed_to_guests(self):
		response = h.request(self.client.post, "/api/method/platform_core.api.auth.logout")
		self.assertEqual(response.status_code, 403)

	def test_logout_closes_session_and_returns_keycloak_url(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(h.logged_user(self.client), h.AYSE)
		response = h.request(self.client.post, "/api/method/platform_core.api.auth.logout")
		self.assertEqual(response.status_code, 200, response.data[:300])
		url = response.json["message"]["logout_url"]
		self.assertTrue(
			url.startswith("http://kimlik.localhost:8660/realms/platform/protocol/openid-connect/logout?")
		)
		self.assertIn("client_id=site-kiraci1", url)
		self.assertIn("post_logout_redirect_uri=http%3A%2F%2Fkiraci1.localhost%3A8661%2Fpanel", url)
		self.assertEqual(h.logged_user(self.client), "Guest")
		self.assertEqual(h.session_count(h.AYSE), 0)
