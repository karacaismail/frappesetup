"""Service token tests (`auth_hooks`). Rules: docs/sozlesmeler.md section 3, AU-3 and AU-5.

Expected rejections: wrong `aud`, wrong `azp`, expired, unsigned, wrong `iss`, several `aud` values,
a request carrying `cmd`, a token together with a session cookie, a call without a token.
"""

from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

ENDPOINT = "/api/method/platform_core.api.identity.set_enabled"
BODY = {"issuer": h.ISSUER, "subject": "sub-ayse", "enabled": True}


class TestServiceToken(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.key = h.Key()
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
		h.make_link("sub-ayse", h.AYSE)

	def call(self, token=None, client=None, path=ENDPOINT, body=BODY, **extra):
		headers = {"Authorization": f"Bearer {token}"} if token else {}
		return h.request((client or h.new_client()).post, path, json=body, headers=headers, **extra)

	def test_valid_token_is_accepted(self):
		response = self.call(self.key.sign(h.access_payload()))
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"user": h.AYSE, "enabled": True})

	def test_broken_tokens_get_401(self):
		now = h.access_payload()["iat"]
		cases = {
			"wrong_aud": self.key.sign(h.access_payload(aud="press")),
			"several_aud": self.key.sign(h.access_payload(aud=["site-kiraci1", "press"])),
			"wrong_azp": self.key.sign(h.access_payload(azp="press-service")),
			"expired": self.key.sign(h.access_payload(exp=now - 120)),
			"unsigned": self.key.sign(h.access_payload(), alg="none"),
			"wrong_key": h.Key("other").sign(h.access_payload()),
			"wrong_iss": self.key.sign(h.access_payload(iss="http://attacker.example/realms/platform")),
			"no_exp": self.key.sign(h.access_payload(exp=None)),
		}
		for name, token in cases.items():
			response = self.call(token)
			self.assertEqual(response.status_code, 401, f"{name}: {response.data[:200]}")
			self.assertEqual(response.json.get("exc_type"), "ServiceTokenRejected", name)

	def test_thirty_second_leeway_is_accepted(self):
		now = h.access_payload()["iat"]
		response = self.call(self.key.sign(h.access_payload(exp=now - 10)))
		self.assertEqual(response.status_code, 200, response.data[:300])

	def test_request_with_cmd_field_is_rejected(self):
		# A JSON request ignores query arguments (frappe/app.py:340), so `cmd` travels in the body.
		response = self.call(
			self.key.sign(h.access_payload()), body={**BODY, "cmd": "frappe.auth.get_logged_user"}
		)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json.get("exc_type"), "ServiceTokenRejected")

	def test_session_cookie_together_with_token_is_rejected(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(h.logged_user(client), h.AYSE)
		response = self.call(self.key.sign(h.access_payload()), client=client)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json.get("exc_type"), "ServiceTokenRejected")

	def test_call_without_token_is_rejected(self):
		guest = self.call(None)
		self.assertEqual(guest.status_code, 403)
		admin = h.new_client()
		admin.set_cookie("sid", self.sid)
		response = self.call(None, client=admin)
		self.assertEqual(response.status_code, 403, "a session alone must not open the service endpoint")

	def test_token_does_not_open_other_endpoints(self):
		response = h.request(
			h.new_client().get,
			"/api/method/frappe.auth.get_logged_user",
			headers={"Authorization": f"Bearer {self.key.sign(h.access_payload())}"},
		)
		self.assertEqual(response.status_code, 401)

	def test_unavailable_keys_give_503_not_a_bypass(self):
		with h.jwks_unavailable_patch():
			response = self.call(self.key.sign(h.access_payload()))
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.json.get("exc_type"), "KeycloakKeysUnavailable")
