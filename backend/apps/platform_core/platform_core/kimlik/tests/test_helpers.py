"""Tests of the Frappe-independent helpers. No database needed."""

from frappe.tests import UnitTestCase

from platform_core.kimlik import helpers


class TestPureHelpers(UnitTestCase):
	def test_issuer_url_follows_contract(self):
		# docs/sozlesmeler.md section 2: iss = <keycloak_public_url>/realms/platform
		self.assertEqual(
			helpers.issuer_url("http://kimlik.localhost:8660/", "platform"),
			"http://kimlik.localhost:8660/realms/platform",
		)

	def test_jwks_url(self):
		self.assertEqual(
			helpers.jwks_url("http://kimlik.localhost:8660", "platform"),
			"http://kimlik.localhost:8660/realms/platform/protocol/openid-connect/certs",
		)

	def test_end_session_url(self):
		url = helpers.end_session_url(
			"http://kimlik.localhost:8660", "platform", "site-kiraci1", "http://kiraci1.localhost:8661/panel"
		)
		self.assertTrue(
			url.startswith("http://kimlik.localhost:8660/realms/platform/protocol/openid-connect/logout?")
		)
		self.assertIn("client_id=site-kiraci1", url)
		self.assertIn("post_logout_redirect_uri=http%3A%2F%2Fkiraci1.localhost%3A8661%2Fpanel", url)
		self.assertNotIn("id_token_hint", url)

	def test_safe_redirect_accepts_only_relative_paths(self):
		for path in ("/panel", "/panel?tab=1", "/app/todo", "/"):
			self.assertTrue(helpers.is_safe_redirect(path), path)
		for path in (
			"https://evil.example/",
			"//evil.example/panel",
			"/\\evil.example",
			"panel",
			"",
			None,
			"/panel\nSet-Cookie: a=b",
			"/panel\\x",
			"javascript:alert(1)",
			"/" + "a" * 2048,
		):
			self.assertFalse(helpers.is_safe_redirect(path), repr(path))

	def test_session_id_format(self):
		self.assertTrue(helpers.is_session_id("11111111-1111-4111-8111-111111111111"))
		self.assertFalse(helpers.is_session_id("a%b"))
		self.assertFalse(helpers.is_session_id("a_b"))
		self.assertFalse(helpers.is_session_id(""))
		self.assertFalse(helpers.is_session_id(None))

	def test_session_marker_matches_frappe_json_separators(self):
		self.assertEqual(helpers.session_marker("abc"), '"keycloak_sid":"abc"')

	def test_session_claims(self):
		claims = {"sub": "s-1", "sid": "k-1-long-enough", "email": "x@example.test"}
		self.assertEqual(
			helpers.session_claims(claims, "http://kimlik.localhost:8660/realms/platform"),
			{
				"keycloak_iss": "http://kimlik.localhost:8660/realms/platform",
				"keycloak_sub": "s-1",
				"keycloak_sid": "k-1-long-enough",
			},
		)
		self.assertNotIn("keycloak_sid", helpers.session_claims({"sub": "s-1"}, "iss"))

	def test_email_verified_accepts_bool_and_true_string(self):
		self.assertTrue(helpers.email_verified({"email_verified": True}))
		self.assertTrue(helpers.email_verified({"email_verified": "true"}))
		self.assertFalse(helpers.email_verified({"email_verified": False}))
		self.assertFalse(helpers.email_verified({"email_verified": "false"}))
		self.assertFalse(helpers.email_verified({}))
