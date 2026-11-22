"""Tests of the Frappe-independent helpers. No database needed."""

from frappe.tests import UnitTestCase

from platform_core.identity import helpers


class TestPureHelpers(UnitTestCase):
	def test_issuer_url_follows_contract(self):
		# docs/sozlesmeler.md section 2: iss = <keycloak_public_url>/realms/platform
		self.assertEqual(
			helpers.issuer_url("http://identity.localhost:8660/", "platform"),
			"http://identity.localhost:8660/realms/platform",
		)

	def test_jwks_url(self):
		self.assertEqual(
			helpers.jwks_url("http://identity.localhost:8660", "platform"),
			"http://identity.localhost:8660/realms/platform/protocol/openid-connect/certs",
		)

	def test_end_session_url(self):
		url = helpers.end_session_url(
			"http://identity.localhost:8660",
			"platform",
			"site-tenant1",
			"http://tenant1.localhost:8661/panel",
		)
		self.assertTrue(
			url.startswith("http://identity.localhost:8660/realms/platform/protocol/openid-connect/logout?")
		)
		self.assertIn("client_id=site-tenant1", url)
		self.assertIn("post_logout_redirect_uri=http%3A%2F%2Ftenant1.localhost%3A8661%2Fpanel", url)
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
		self.assertTrue(helpers.is_session_id("Synthetic_-Example123456"))
		self.assertFalse(helpers.is_session_id("long%enough"))
		self.assertFalse(helpers.is_session_id("long-enough\n"))
		self.assertFalse(helpers.is_session_id("long/enough"))
		self.assertFalse(helpers.is_session_id("a" * 65))
		self.assertFalse(helpers.is_session_id("a_b"))
		self.assertFalse(helpers.is_session_id(""))
		self.assertFalse(helpers.is_session_id(None))

	def test_session_claims(self):
		claims = {"sub": "s-1", "sid": "k-1-long-enough", "email": "x@example.test"}
		self.assertEqual(
			helpers.session_claims(claims, "http://identity.localhost:8660/realms/platform"),
			{
				"keycloak_iss": "http://identity.localhost:8660/realms/platform",
				"keycloak_sub": "s-1",
				"keycloak_sid": "k-1-long-enough",
			},
		)
		self.assertNotIn("keycloak_sid", helpers.session_claims({"sub": "s-1"}, "iss"))

	def test_normalize_path_matches_frappe_website_resolution(self):
		for raw, expected in (
			("//me", "/me"),
			("/me.html", "/me"),
			("/./me", "/me"),
			("/me/", "/me"),
			("/a/../me", "/me"),
			("/update-password/x", "/update-password/x"),
			("/", "/"),
		):
			self.assertEqual(helpers.normalize_path(raw), expected, raw)

	def test_pkce_challenge_is_base64url_sha256(self):
		self.assertEqual(
			helpers.code_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
			"E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
		)

	def test_email_verified_accepts_bool_and_true_string(self):
		self.assertTrue(helpers.email_verified({"email_verified": True}))
		self.assertTrue(helpers.email_verified({"email_verified": "true"}))
		self.assertFalse(helpers.email_verified({"email_verified": False}))
		self.assertFalse(helpers.email_verified({"email_verified": "false"}))
		self.assertFalse(helpers.email_verified({}))
