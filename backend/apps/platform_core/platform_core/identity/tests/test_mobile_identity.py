"""Mobile token verification exposed by `platform_core.identity.api` for platform-core-mobil (AU-3, AU-4, AU-5).

The real mobile endpoints are not in this branch; a stub under the tests package stands in for them and
`MOBILE_PATH_PREFIX` is pointed at it for the duration of the tests.
"""

from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import api as identity_api
from platform_core.identity import provider_setup
from platform_core.identity.tests import helpers as h
from platform_core.identity.tests import mobile_stub

STUB = "/api/method/platform_core.identity.tests.mobile_stub.v1_whoami"
STUB_PREFIX = "/api/method/platform_core.identity.tests.mobile_stub.v1_"


AUTH_TIME = 1795300000


def mobile_payload(**overrides) -> dict:
	payload = h.access_payload(
		sub="sub-ayse",
		azp="mobile",
		scope="openid mobile",
		sid="11111111-1111-4111-8111-111111111111",
		auth_time=AUTH_TIME,
	)
	payload.update(overrides)
	return {k: v for k, v in payload.items() if v is not None}


def authenticate_mobile_before_platform_hooks():
	"""Models an installed app authenticating the phone before Platform Core runs."""
	token = frappe.get_request_header("Authorization").removeprefix("Bearer ")
	identity_api.authenticate_mobile_request(token)


class TestMobileIdentity(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(h.SiteSettings({"kimlik_mobil_azp": ["mobile"]}))
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)
		cls.prefix = patch("platform_core.identity.helpers.MOBILE_PATH_PREFIX", STUB_PREFIX)
		cls.prefix.start()
		cls.addClassCleanup(cls.prefix.stop)
		cls.addClassCleanup(mobile_stub.register())

	@classmethod
	def tearDownClass(cls):
		h.clear_links()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links()
		h.make_link("sub-ayse", h.AYSE)

	def call(self, token=None, client=None, path=STUB, headers=None, **extra):
		client = client or h.new_client()
		headers = dict(headers or {})
		if token:
			headers["Authorization"] = f"Bearer {token}"
		headers.update(h.csrf_headers(client))
		return h.request(client.post, path, json={}, headers=headers, **extra)

	def test_valid_mobile_token_sets_user_and_identity(self):
		response = self.call(self.key.sign(mobile_payload()))
		self.assertEqual(response.status_code, 200, response.data[:300])
		body = response.json["message"]
		self.assertEqual(body["user"], h.AYSE)
		identity = body["identity"]
		self.assertEqual(identity["account"], h.AYSE)
		self.assertEqual(identity["issuer"], h.ISSUER)
		self.assertEqual(identity["subject"], "sub-ayse")
		self.assertEqual(identity["sid"], "11111111-1111-4111-8111-111111111111")

	def test_mobile_access_token_keeps_base64url_session_id(self):
		sid = "Synthetic_-Example123456"
		response = self.call(self.key.sign(mobile_payload(sid=sid)))
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"]["identity"]["sid"], sid)

	def test_mobile_identity_from_an_earlier_hook_survives_platform_hooks(self):
		real_get_hooks = frappe.get_hooks

		def get_hooks(hook=None, *args, **kwargs):
			value = real_get_hooks(hook, *args, **kwargs)
			if hook == "auth_hooks":
				return [f"{__name__}.authenticate_mobile_before_platform_hooks", *value]
			return value

		browser = h.new_client()
		h.login_with_keycloak(browser, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(h.logged_user(browser), h.AYSE)
		token = self.key.sign(mobile_payload())

		with patch.object(frappe, "get_hooks", side_effect=get_hooks):
			response = self.call(token)
			with_cookie = self.call(token, client=browser)

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"]["identity"]["account"], h.AYSE)
		self.assertEqual(with_cookie.status_code, 401)
		self.assertEqual(with_cookie.json.get("exc_type"), "ServiceTokenRejected")

	def test_mobile_identity_matches_the_contract(self):
		# docs/sozlesmeler.md section 3, mobile identity: account, scope, site, installation and sid are text.
		# scope is always the text "mobile". site is the site of the request.
		token = self.key.sign(mobile_payload())
		response = self.call(token, headers={"X-Platform-Installation": "inst-0001_ab"})
		self.assertEqual(response.status_code, 200, response.data[:300])
		body = response.json["message"]
		identity = body["identity"]
		for field in ("account", "scope", "site", "installation", "sid"):
			self.assertIsInstance(identity.get(field), str, field)
		self.assertEqual(identity["scope"], "mobile")
		self.assertEqual(identity["site"], body["site"])
		self.assertEqual(identity["installation"], "inst-0001_ab")
		self.assertNotIn("user", identity)
		# Fields that the mobile module reads in addition (mobil/request.py): issuer, subject and iat.
		self.assertIsInstance(identity["iat"], int)

	def test_mobile_identity_carries_auth_time(self):
		# docs/sozlesmeler.md section 3, mobile identity: auth_time is the token claim, an integer (Unix seconds).
		response = self.call(self.key.sign(mobile_payload()))
		self.assertEqual(response.status_code, 200, response.data[:300])
		value = response.json["message"]["identity"]["auth_time"]
		self.assertIs(type(value), int)
		self.assertEqual(value, AUTH_TIME)

	def test_token_without_integer_auth_time_is_not_a_phone_request(self):
		# "If the value is missing or malformed, the request is not a phone request."
		for bad in (None, "1795300000", 1795300000.5, True):
			response = self.call(self.key.sign(mobile_payload(auth_time=bad)))
			self.assertEqual(response.status_code, 401, f"{bad!r}: {response.data[:200]}")
			self.assertEqual(response.json.get("exc_type"), "ServiceTokenRejected", repr(bad))

	def test_bad_installation_header_gives_an_empty_installation(self):
		for value in ("", "a" * 129, "bad value", "<x>"):
			response = self.call(self.key.sign(mobile_payload()), headers={"X-Platform-Installation": value})
			self.assertEqual(response.status_code, 200, response.data[:300])
			self.assertEqual(response.json["message"]["identity"]["installation"], "", value)

	def test_bad_mobile_tokens_get_401(self):
		now = mobile_payload()["iat"]
		cases = {
			"wrong_aud": self.key.sign(mobile_payload(aud="press")),
			"wrong_azp": self.key.sign(mobile_payload(azp="identity-sync")),
			"service_scope_only": self.key.sign(mobile_payload(scope="openid")),
			"expired": self.key.sign(mobile_payload(exp=now - 120)),
			"unsigned": self.key.sign(mobile_payload(), alg="none"),
			"wrong_iss": self.key.sign(mobile_payload(iss="http://attacker.example/realms/platform")),
			"unknown_identity": self.key.sign(mobile_payload(sub="sub-unknown")),
		}
		for name, token in cases.items():
			response = self.call(token)
			self.assertEqual(response.status_code, 401, f"{name}: {response.data[:200]}")
			self.assertEqual(response.json.get("exc_type"), "ServiceTokenRejected", name)

	def test_disabled_user_is_refused(self):
		import frappe

		frappe.db.set_value("User", h.AYSE, "enabled", 0)
		h.refresh()
		self.addCleanup(lambda: (frappe.db.set_value("User", h.AYSE, "enabled", 1), h.refresh()))
		response = self.call(self.key.sign(mobile_payload()))
		self.assertEqual(response.status_code, 401)

	def test_cookie_or_cmd_with_token_is_refused_and_options_ignores_token(self):
		token = self.key.sign(mobile_payload())
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
		with_cookie = self.call(token, client=client)
		self.assertEqual(with_cookie.status_code, 401)
		with_cmd = h.request(
			h.new_client().post,
			STUB,
			json={"cmd": "frappe.auth.get_logged_user"},
			headers={"Authorization": f"Bearer {token}"},
		)
		self.assertEqual(with_cmd.status_code, 401)
		# Preflight: the hook does not look at the token (AU-5). Frappe itself still answers 401 to a
		# Bearer request whose user stays Guest (frappe/auth.py:649), with its generic error, not ours.
		options = h.request(h.new_client().options, STUB, headers={"Authorization": "Bearer not-a-token"})
		self.assertEqual(options.status_code, 401)
		self.assertEqual(options.json.get("exc_type"), "AuthenticationError")

	def test_mobile_token_opens_nothing_else(self):
		token = self.key.sign(mobile_payload())
		other = h.request(
			h.new_client().post,
			"/api/method/platform_core.api.identity.set_enabled",
			json={"issuer": h.ISSUER, "subject": "sub-ayse", "enabled": True},
			headers={"Authorization": f"Bearer {token}"},
		)
		self.assertEqual(other.status_code, 401, "a mobile token is not a service token")
		generic = h.request(
			h.new_client().get,
			"/api/method/frappe.auth.get_logged_user",
			headers={"Authorization": f"Bearer {token}"},
		)
		self.assertEqual(generic.status_code, 401)


class TestMobileStubIsNotAnEndpoint(FrappeAPITestCase):
	"""On a running site the stub is not whitelisted: nobody can call it through `/api/method`."""

	def test_stub_is_not_whitelisted_without_a_test(self):
		self.assertNotIn(mobile_stub.v1_whoami, frappe.whitelisted)
		guest = h.request(h.new_client().post, STUB, json={})
		self.assertEqual(guest.status_code, 403, guest.data[:300])
		self.assertEqual(guest.json.get("exc_type"), "PermissionError")

	def test_register_refuses_outside_tests(self):
		with patch.object(frappe, "in_test", False):
			with self.assertRaises(RuntimeError):
				mobile_stub.register()
