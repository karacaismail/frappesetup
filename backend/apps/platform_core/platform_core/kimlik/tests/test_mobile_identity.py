"""Mobile token verification exposed by `platform_core.kimlik.api` for platform-core-mobil (AU-3, AU-4, AU-5).

The real mobile endpoints are not in this branch; a stub under the tests package stands in for them and
`MOBILE_PATH_PREFIX` is pointed at it for the duration of the tests.
"""

from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h
from platform_core.kimlik.tests import mobile_stub

STUB = "/api/method/platform_core.kimlik.tests.mobile_stub.v1_whoami"
STUB_PREFIX = "/api/method/platform_core.kimlik.tests.mobile_stub.v1_"


def mobile_payload(**overrides) -> dict:
	payload = h.access_payload(
		sub="sub-ayse", azp="mobile", scope="openid mobile", sid="11111111-1111-4111-8111-111111111111"
	)
	payload.update(overrides)
	return {k: v for k, v in payload.items() if v is not None}


class TestMobileIdentity(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)
		cls.prefix = patch("platform_core.kimlik.helpers.MOBILE_PATH_PREFIX", STUB_PREFIX)
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

	def call(self, token=None, client=None, path=STUB, **extra):
		client = client or h.new_client()
		headers = {"Authorization": f"Bearer {token}"} if token else {}
		headers.update(h.csrf_headers(client))
		return h.request(client.post, path, json={}, headers=headers, **extra)

	def test_valid_mobile_token_sets_user_and_identity(self):
		response = self.call(self.key.sign(mobile_payload()))
		self.assertEqual(response.status_code, 200, response.data[:300])
		body = response.json["message"]
		self.assertEqual(body["user"], h.AYSE)
		self.assertEqual(body["identity"]["user"], h.AYSE)
		self.assertEqual(body["identity"]["issuer"], h.ISSUER)
		self.assertEqual(body["identity"]["subject"], "sub-ayse")
		self.assertEqual(body["identity"]["sid"], "11111111-1111-4111-8111-111111111111")
		self.assertEqual(body["identity"]["azp"], "mobile")

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
