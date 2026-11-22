"""Keycloak back-channel logout tests (OpenID Connect Back-Channel Logout).

Expected behaviour comes from docs/sozlesmeler.md section 3 (logout token rules) and section 4
(`sid` matching). Tokens are signed with a local RSA key.
"""

from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

ENDPOINT = "/api/method/platform_core.api.keycloak_backchannel_logout"
SID = "11111111-1111-4111-8111-111111111111"


class TestBackChannelLogout(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		for email in h.SAMPLE_USERS:
			h.ensure_user(email)
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
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

	def send(self, token, client=None):
		client = client or h.new_client()
		return h.request(
			client.post,
			ENDPOINT,
			data={"logout_token": token} if token is not None else {},
			content_type="application/x-www-form-urlencoded",
			headers=h.csrf_headers(client),
		)

	def test_invalid_tokens_are_rejected(self):
		cases = {
			"missing": None,
			"malformed": "abc.def",
			"wrong_key": h.Key("other-kid").sign(h.logout_payload()),
			"none_algorithm": self.key.sign(h.logout_payload(), alg="none"),
			"wrong_iss": self.key.sign(h.logout_payload(iss="http://attacker.example/realms/platform")),
			"wrong_aud": self.key.sign(h.logout_payload(aud="press")),
			"nonce_present": self.key.sign(h.logout_payload(nonce="n-1")),
			"no_event": self.key.sign(h.logout_payload(events={})),
			"no_sid_no_sub": self.key.sign(h.logout_payload(sid=None, sub=None)),
			# OpenID Connect Back-Channel Logout 1.0, section 2.4: exp and jti are required,
			# the event value must be a JSON object, sid must be a string.
			"no_exp": self.key.sign(h.logout_payload(exp=None)),
			"no_jti": self.key.sign(h.logout_payload(jti=None)),
			"event_value_null": self.key.sign(h.logout_payload(events={h.LOGOUT_EVENT: None})),
			"numeric_sid": self.key.sign(h.logout_payload(sid=12345)),
		}
		for name, token in cases.items():
			response = self.send(token)
			self.assertEqual(response.status_code, 400, f"{name}: {response.data[:200]}")
			self.assertEqual(response.json.get("exc_type"), "InvalidLogoutToken", name)

	def test_valid_token_closes_session_by_sid(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		self.assertEqual(h.logged_user(self.client), h.AYSE)
		response = self.send(self.key.sign(h.logout_payload(sub="sub-ayse", sid=SID)))
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"closed_sessions": 1})
		self.assertEqual(response.headers.get("Cache-Control"), "no-store")
		self.assertEqual(h.logged_user(self.client), "Guest")
		self.assertEqual(h.session_count(h.AYSE), 0)

	def test_unmatched_sid_falls_back_to_sub_and_closes_all_sessions(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE))
		second = h.new_client()
		h.login_with_keycloak(second, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(h.session_count(h.AYSE), 2)
		response = self.send(
			self.key.sign(h.logout_payload(sub="sub-ayse", sid="22222222-2222-4222-8222-222222222222"))
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"], {"closed_sessions": 2})
		self.assertEqual(h.logged_user(self.client), "Guest")
		self.assertEqual(h.logged_user(second), "Guest")

	def test_other_users_sessions_are_untouched(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		mehmet = h.new_client()
		h.login_with_keycloak(
			mehmet, h.userinfo("sub-mehmet", h.MEHMET, sid="33333333-3333-4333-8333-333333333333")
		)
		response = self.send(self.key.sign(h.logout_payload(sub="sub-ayse", sid=SID)))
		self.assertEqual(response.json["message"], {"closed_sessions": 1})
		self.assertEqual(h.logged_user(self.client), "Guest")
		self.assertEqual(h.logged_user(mehmet), h.MEHMET)

	def test_unknown_identity_returns_200_and_closes_nothing(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		response = self.send(
			self.key.sign(h.logout_payload(sub="sub-unknown", sid="44444444-4444-4444-8444-444444444444"))
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"], {"closed_sessions": 0})
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	def test_request_with_session_cookie_is_rejected(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		response = self.send(self.key.sign(h.logout_payload(sub="sub-ayse", sid=SID)), client=self.client)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "InvalidLogoutToken")
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	def test_replayed_token_is_rejected_and_spares_new_sessions(self):
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		token = self.key.sign(h.logout_payload(sub="sub-ayse", sid=SID))
		first = self.send(token)
		self.assertEqual(first.json["message"], {"closed_sessions": 1})
		fresh = h.new_client()
		h.login_with_keycloak(
			fresh, h.userinfo("sub-ayse", h.AYSE, sid="55555555-5555-4555-8555-555555555555")
		)
		second = self.send(token)
		self.assertEqual(second.status_code, 400, second.data[:200])
		self.assertEqual(second.json.get("exc_type"), "InvalidLogoutToken")
		self.assertEqual(h.logged_user(fresh), h.AYSE)

	def test_sub_fallback_spares_sessions_opened_after_the_token(self):
		old_iat = h.logout_payload()["iat"] - 120
		token = self.key.sign(
			h.logout_payload(sub="sub-ayse", sid="66666666-6666-4666-8666-666666666666", iat=old_iat)
		)
		h.login_with_keycloak(self.client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		response = self.send(token)
		self.assertEqual(response.status_code, 200, response.data[:200])
		self.assertEqual(response.json["message"], {"closed_sessions": 0})
		self.assertEqual(h.logged_user(self.client), h.AYSE)

	def test_get_is_rejected(self):
		# Frappe answers a wrong HTTP method with PermissionError (frappe/handler.py:110).
		response = h.request(h.new_client().get, ENDPOINT)
		self.assertEqual(response.status_code, 403)
