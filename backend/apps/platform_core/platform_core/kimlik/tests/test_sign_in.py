"""Sign-in through this app's own Keycloak callback. Requests go through the real HTTP path (D-6).

Expected behaviour comes from docs/sozlesmeler.md sections 4 and 5 (D-1):
- `get_login_url` creates `state`, PKCE and `nonce` on the server and binds the attempt to a browser cookie,
- the callback consumes `state` exactly once and refuses a foreign browser,
- the right user signs in, the identity link is created only with a verified e-mail,
- a different `sub` cannot sign in with the same e-mail, a foreign link is refused,
- the Keycloak session id from the ID token is stored in the Frappe session.
"""

import base64
import hashlib

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
		h.exchange_calls.clear()
		self.client = h.new_client()

	def test_hooks_are_wired(self):
		self.assertNotIn("platform_core.kimlik.sign_in.on_social_login", frappe.get_hooks("on_social_login"))
		self.assertIn("platform_core.kimlik.service_token.validate", frappe.get_hooks("auth_hooks"))
		self.assertIn("platform_core.kimlik.login_policy.before_login", frappe.get_hooks("before_login"))
		self.assertIn("platform_core.kimlik.login_policy.before_request", frappe.get_hooks("before_request"))
		overrides = frappe.get_hooks("override_whitelisted_methods")
		self.assertIn(
			"platform_core.kimlik.login_policy.send_login_link",
			overrides.get("frappe.www.login.send_login_link", []),
		)

	def test_get_login_url_binds_browser_and_uses_pkce(self):
		response, query = h.start_login(self.client, "/panel", headers={"Accept-Language": "tr"})
		self.assertEqual(response.status_code, 200, response.data[:300])
		result = response.json["message"]
		self.assertTrue(
			result["login_url"].startswith(
				"http://kimlik.localhost:8660/realms/platform/protocol/openid-connect/auth?"
			)
		)
		self.assertEqual(query["client_id"], "site-kiraci1")
		self.assertEqual(query["response_type"], "code")
		self.assertEqual(query["scope"], "openid")
		self.assertEqual(query["redirect_uri"], "http://kiraci1.localhost:8661" + h.CALLBACK)
		self.assertEqual(query["code_challenge_method"], "S256")
		self.assertGreaterEqual(len(query["state"]), 32)
		self.assertGreaterEqual(len(query["nonce"]), 32)
		self.assertGreaterEqual(len(query["code_challenge"]), 43)
		self.assertEqual(result["brand_name"], "Atonota")
		self.assertEqual(result["label"], "Atonota ile oturum aç")
		cookie = next(
			(c for c in response.headers.getlist("Set-Cookie") if c.startswith(f"{h.LOGIN_COOKIE}=")), ""
		)
		self.assertTrue(cookie, response.headers.getlist("Set-Cookie"))
		self.assertIn("HttpOnly", cookie)
		self.assertIn("SameSite=Lax", cookie)
		self.assertIn("Max-Age=600", cookie)

	def test_right_user_signs_in_and_link_is_created(self):
		_started, query = h.start_login(self.client, "/panel")
		response = h.finish_login(
			self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		)
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
		self.assertEqual(len(h.sessions_containing(f'"keycloak_sid":"{SID}"')), 1)
		# PKCE: the verifier sent to Keycloak must hash to the challenge of the authorize request.
		verifier = h.exchange_calls[-1]["code_verifier"]
		digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
		self.assertEqual(digest, query["code_challenge"])
		self.assertEqual(h.exchange_calls[-1]["redirect_uri"], "http://kiraci1.localhost:8661" + h.CALLBACK)
		# The login cookie is cleared after use.
		cleared = [c for c in response.headers.getlist("Set-Cookie") if c.startswith(f"{h.LOGIN_COOKIE}=")]
		self.assertTrue(
			cleared and "Expires=" in cleared[0] and f"{h.LOGIN_COOKIE}=;" in cleared[0].replace('""', "")
		)

	def test_csrf_token_exists_right_after_sign_in(self):
		# Frappe skips the CSRF check while the session has no token (frappe/auth.py:92).
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		self.assertTrue(h.csrf_token_of(self.client))
		without = h.request(self.client.post, "/api/method/platform_core.api.auth.logout")
		self.assertEqual(without.status_code, 400, without.data[:200])
		self.assertEqual(without.json.get("exc_type"), "CSRFTokenError")
		self.assertEqual(h.logged_user(self.client), h.AYSE)
		with_token = h.request(
			self.client.post, "/api/method/platform_core.api.auth.logout", headers=h.csrf_headers(self.client)
		)
		self.assertEqual(with_token.status_code, 200, with_token.data[:200])

	def test_default_redirect_is_panel_url(self):
		_started, query = h.start_login(self.client)
		response = h.finish_login(self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE)))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers["Location"], "http://kiraci1.localhost:8661/panel")

	def test_callback_from_another_browser_is_refused(self):
		# Login CSRF: the attacker starts a login and hands state and code to a victim browser.
		_started, query = h.start_login(self.client)
		victim = h.new_client()
		h.start_login(victim)  # the victim has its own cookie
		response = h.finish_login(victim, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE)))
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(h.logged_user(victim), "Guest")
		# The state was consumed by the failed attempt, so the attacker cannot complete it either.
		response = h.finish_login(self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE)))
		self.assertEqual(response.status_code, 400)

	def test_callback_without_cookie_is_refused(self):
		_started, query = h.start_login(self.client)
		stranger = h.new_client()
		response = h.finish_login(stranger, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE)))
		self.assertEqual(response.status_code, 400, response.data[:300])
		self.assertEqual(h.logged_user(stranger), "Guest")

	def test_state_is_single_use_and_unknown_state_is_refused(self):
		_started, query = h.start_login(self.client)
		token = h.id_token(query, h.userinfo("sub-ayse", h.AYSE))
		first = h.finish_login(self.client, query, token)
		self.assertEqual(first.status_code, 302)
		second = h.finish_login(h.new_client(), query, token)
		self.assertEqual(second.status_code, 400)
		# A signed-in Website User may not call guest endpoints: the shell's method allow list answers 403
		# before the callback runs (docs/sozlesmeler.md, Website User allow list). A guest gets 400.
		forged = h.finish_login(self.client, query, token, state="forged-state-value")
		self.assertIn(forged.status_code, (400, 403))
		missing = h.request(self.client.get, h.CALLBACK, query_string={"code": "x"})
		self.assertIn(missing.status_code, (400, 403))
		guest_missing = h.request(h.new_client().get, h.CALLBACK, query_string={"code": "x"})
		self.assertEqual(guest_missing.status_code, 400)

	def test_wrong_nonce_or_bad_id_token_is_refused(self):
		_started, query = h.start_login(self.client)
		response = h.finish_login(
			self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE), nonce="other")
		)
		self.assertEqual(response.status_code, 400, response.data[:300])
		self.assertEqual(h.logged_user(self.client), "Guest")
		_started, query = h.start_login(self.client)
		foreign_key = h.Key("foreign")
		response = h.finish_login(
			self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE), foreign_key)
		)
		self.assertEqual(response.status_code, 400)
		_started, query = h.start_login(self.client)
		response = h.finish_login(
			self.client, query, h.id_token(query, h.userinfo("sub-ayse", h.AYSE), aud="press")
		)
		self.assertEqual(response.status_code, 400)

	def test_oversized_code_or_state_is_refused(self):
		_started, query = h.start_login(self.client)
		long_state = h.finish_login(self.client, query, "x", state="s" * 300)
		self.assertEqual(long_state.status_code, 400)
		long_code = h.finish_login(self.client, query, "x", code="c" * 5000)
		self.assertEqual(long_code.status_code, 400)
		big_body = h.request(
			self.client.post,
			"/api/method/platform_core.api.auth.get_login_url",
			json={"redirect_to": "/panel", "padding": "p" * 20000},
		)
		self.assertEqual(big_body.status_code, 413)

	def test_keycloak_error_response_is_shown_not_trusted(self):
		_started, query = h.start_login(self.client)
		response = h.request(
			self.client.get,
			h.CALLBACK,
			query_string={"state": query["state"], "error": "access_denied", "error_description": "x"},
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(h.logged_user(self.client), "Guest")

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

	def test_link_owned_by_another_user_is_refused(self):
		# AU-4: the identity is linked to Mehmet but the token now carries another user's e-mail. Nobody signs in.
		h.make_link("sub-mehmet", h.MEHMET)
		response = h.login_with_keycloak(self.client, h.userinfo("sub-mehmet", h.AYSE))
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_linked_user_signs_in_without_email_claim(self):
		h.make_link("sub-mehmet", h.MEHMET)
		claims = h.userinfo("sub-mehmet", h.MEHMET)
		claims.pop("email")
		response = h.login_with_keycloak(self.client, claims)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(h.logged_user(self.client), h.MEHMET)

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
		self.assertEqual(response.status_code, 403)
		self.assertEqual(h.logged_user(self.client), "Guest")

	def test_email_case_is_normalised(self):
		response = h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE.upper()))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	def test_get_login_url_rejects_external_redirect(self):
		for target in ("https://evil.example/", "//evil.example/panel", "panel", "/pa\\nel"):
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

	def test_get_login_url_returns_503_when_settings_are_missing(self):
		with h.SiteSettings({"keycloak_client_secret": ""}):
			response = h.request(
				self.client.post, "/api/method/platform_core.api.auth.get_login_url", json={}
			)
		self.assertEqual(response.status_code, 503, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "KeycloakLoginNotConfigured")

	def test_logout_is_closed_to_guests(self):
		response = h.request(self.client.post, "/api/method/platform_core.api.auth.logout")
		self.assertEqual(response.status_code, 403)

	def test_logout_closes_session_and_returns_keycloak_url(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(h.logged_user(self.client), h.AYSE)
		response = h.request(
			self.client.post, "/api/method/platform_core.api.auth.logout", headers=h.csrf_headers(self.client)
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		url = response.json["message"]["logout_url"]
		self.assertTrue(
			url.startswith("http://kimlik.localhost:8660/realms/platform/protocol/openid-connect/logout?")
		)
		self.assertIn("client_id=site-kiraci1", url)
		self.assertIn("post_logout_redirect_uri=http%3A%2F%2Fkiraci1.localhost%3A8661%2Fpanel", url)
		self.assertEqual(h.logged_user(self.client), "Guest")
		self.assertEqual(h.session_count(h.AYSE), 0)
