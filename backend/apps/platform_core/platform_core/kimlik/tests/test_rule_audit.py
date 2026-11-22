"""Regression tests for the failures of the rule self-audit (status file, 22 November 2026).

Expected behaviour comes from the rule files (D-1):
- T-4: the Keycloak `sid` index expires and is deleted under the same Redis key that holds its members,
- G-11 and S-ISL-6: `redirect-to` cannot inject markup into the `/login` page,
- G-7 and S-GIR-4: identity, logout and gated sign-in endpoints are rate limited,
- S-API-1 and S-SUR-4: every identity endpoint refuses a call without a token and a foreign client,
- S-API-3: an identity request with an unknown field is refused, as the contract says
  (`additionalProperties: false`).
"""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import helpers, provider_setup, sign_in
from platform_core.kimlik.tests import helpers as h

SID = "22222222-2222-4222-8222-222222222222"
IDENTITY = "/api/method/platform_core.api.identity."
BODIES = {
	"provision": {
		"issuer": h.ISSUER,
		"subject": "sub-ayse",
		"email": h.AYSE,
		"email_verified": True,
		"first_name": "Ayse",
		"last_name": "Ornek",
		"enabled": True,
		"role_profiles": [],
	},
	"set_enabled": {"issuer": h.ISSUER, "subject": "sub-ayse", "enabled": True},
	"change_email": {"issuer": h.ISSUER, "subject": "sub-ayse", "new_email": h.AYSE},
	"anonymize_user": {"issuer": h.ISSUER, "subject": "sub-yok"},
}


class TestRuleAudit(FrappeAPITestCase):
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

	def setUp(self):
		super().setUp()
		h.clear_links()
		h.make_link("sub-ayse", h.AYSE)
		h.reset_rate_limits()
		self.addCleanup(h.reset_rate_limits)

	def service(self, name, body, **token):
		signed = self.key.sign(h.access_payload(**token))
		return h.request(
			h.new_client().post, IDENTITY + name, json=body, headers={"Authorization": f"Bearer {signed}"}
		)

	# --- T-4 ----------------------------------------------------------------------------------------

	def test_sid_index_expires_under_the_key_that_holds_its_members(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE, sid=SID))
		frappe_sid = client.get_cookie("sid").value
		name = sign_in._sid_index_name(SID)
		self.assertIn(
			frappe_sid, {m.decode() if isinstance(m, bytes) else m for m in frappe.cache.smembers(name)}
		)
		self.assertGreater(frappe.cache.ttl(frappe.cache.make_key(name)), 0)
		sign_in.forget_keycloak_session(SID, frappe_sid)
		self.assertFalse(frappe.cache.smembers(name))

	# --- G-11 and S-ISL-6 ---------------------------------------------------------------------------

	def test_redirect_with_markup_is_not_safe(self):
		for value in ('/"><svg onload=alert(1)>', "/a'b", "/a<b", "/a>b", '/a"b', "/a`b"):
			self.assertFalse(helpers.is_safe_redirect(value), value)
		self.assertTrue(helpers.is_safe_redirect("/app/todo?status=Open&x=1#top"))

	def test_login_page_does_not_reflect_markup(self):
		payload = '/"><svg onload=alert(1)>'
		response = h.request(h.new_client().get, "/login", query_string={"redirect-to": payload})
		self.assertEqual(response.status_code, 200, response.data[:200])
		html = response.data.decode()
		self.assertNotIn("<svg", html)
		self.assertNotIn("onload=alert", html)

	def test_identity_fields_with_sql_text_are_plain_data(self):
		body = dict(BODIES["set_enabled"], subject="x' OR '1'='1")
		response = self.service("set_enabled", body)
		self.assertEqual(response.status_code, 404, response.data[:200])
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", h.AYSE, "enabled"))

	# --- G-7 and S-GIR-4 ----------------------------------------------------------------------------

	def test_logout_is_rate_limited(self):
		# The limit counts per signed-in user (rate_limit user_based). Sign-in limits are reset between rounds.
		statuses = []
		for _number in range(22):
			for endpoint in ("get_login_url", "keycloak_callback"):
				frappe.cache.delete_keys(f"rl:platform_core.api.auth.{endpoint}")
			client = h.new_client()
			h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
			statuses.append(
				h.request(
					client.post, "/api/method/platform_core.api.auth.logout", headers=h.csrf_headers(client)
				).status_code
			)
		self.assertEqual(statuses[0], 200)
		self.assertIn(429, statuses)

	def test_gated_sign_in_wrapper_is_rate_limited(self):
		with h.SiteSettings({"kimlik_yalniz_keycloak": 1}):
			statuses = [
				h.request(
					h.new_client().get,
					"/api/method/frappe.www.login.login_via_key",
					query_string={"key": "x"},
				).status_code
				for _number in range(25)
			]
		self.assertIn(429, statuses)
		self.assertEqual(set(statuses) - {403, 429}, set())

	def test_identity_endpoints_are_rate_limited(self):
		statuses = {
			self.service("set_enabled", dict(BODIES["set_enabled"], subject="sub-yok")).status_code
			for _number in range(305)
		}
		self.assertIn(429, statuses)

	# --- S-API-1 and S-SUR-4 -------------------------------------------------------------------------

	def test_every_identity_endpoint_refuses_no_token_and_a_foreign_client(self):
		for name, body in BODIES.items():
			anonymous = h.request(h.new_client().post, IDENTITY + name, json=body)
			self.assertIn(anonymous.status_code, (401, 403), f"{name} without token: {anonymous.data[:160]}")
			foreign = self.service(name, body, azp="press-service")
			self.assertIn(foreign.status_code, (401, 403), f"{name} foreign azp: {foreign.data[:160]}")
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", h.AYSE, "enabled"))

	# --- S-API-3 ------------------------------------------------------------------------------------

	def test_unknown_fields_are_refused(self):
		for name, body in BODIES.items():
			response = self.service(name, dict(body, roles=["System Manager"]))
			self.assertEqual(response.status_code, 400, f"{name}: {response.data[:160]}")
			self.assertEqual(response.json.get("exc_type"), "InvalidInput", name)
