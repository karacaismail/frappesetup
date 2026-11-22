"""HTTP access checks for the native sign-in wrappers."""

from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import login_policy
from platform_core.kimlik.tests import helpers as h


class TestGatedEndpointAccess(FrappeAPITestCase):
	def setUp(self):
		super().setUp()
		h.clear_links()
		h.ensure_user(h.AYSE)
		h.refresh()

	def assert_gate_denies(self, name, *, signed_in=False):
		target, methods = next(
			(original, verbs)
			for original, (wrapper, verbs) in login_policy.GATED_FUNCTIONS.items()
			if wrapper == name
		)
		with h.SiteSettings({"kimlik_yalniz_keycloak": 1}), h.jwks_patch():
			client = h.new_client()
			if signed_in:
				h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
				self.assertEqual(h.logged_user(client), h.AYSE)
			method = methods[0].lower()
			payload = {"email": h.MEHMET} if signed_in else {}
			params = {"query_string": payload} if method == "get" else {"data": payload}
			response = h.request(
				getattr(client, method),
				f"/api/method/{target}",
				headers=h.csrf_headers(client),
				**params,
			)
			self.assertEqual(response.status_code, 403)
			self.assertEqual(response.json.get("exc_type"), "PermissionError")

	def test_reset_password_guest_denied(self):
		self.assert_gate_denies("reset_password")

	def test_reset_password_foreign_data_denied(self):
		self.assert_gate_denies("reset_password", signed_in=True)

	def test_update_password_guest_denied(self):
		self.assert_gate_denies("update_password")

	def test_update_password_foreign_data_denied(self):
		self.assert_gate_denies("update_password", signed_in=True)

	def test_sign_up_guest_denied(self):
		self.assert_gate_denies("sign_up")

	def test_sign_up_foreign_data_denied(self):
		self.assert_gate_denies("sign_up", signed_in=True)

	def test_send_login_link_guest_denied(self):
		self.assert_gate_denies("send_login_link")

	def test_send_login_link_foreign_data_denied(self):
		self.assert_gate_denies("send_login_link", signed_in=True)

	def test_login_via_key_guest_denied(self):
		self.assert_gate_denies("login_via_key")

	def test_login_via_key_foreign_data_denied(self):
		self.assert_gate_denies("login_via_key", signed_in=True)

	def test_login_via_token_guest_denied(self):
		self.assert_gate_denies("login_via_token")

	def test_login_via_token_foreign_data_denied(self):
		self.assert_gate_denies("login_via_token", signed_in=True)

	def test_login_via_google_guest_denied(self):
		self.assert_gate_denies("login_via_google")

	def test_login_via_google_foreign_data_denied(self):
		self.assert_gate_denies("login_via_google", signed_in=True)

	def test_login_via_github_guest_denied(self):
		self.assert_gate_denies("login_via_github")

	def test_login_via_github_foreign_data_denied(self):
		self.assert_gate_denies("login_via_github", signed_in=True)

	def test_login_via_facebook_guest_denied(self):
		self.assert_gate_denies("login_via_facebook")

	def test_login_via_facebook_foreign_data_denied(self):
		self.assert_gate_denies("login_via_facebook", signed_in=True)

	def test_login_via_frappe_guest_denied(self):
		self.assert_gate_denies("login_via_frappe")

	def test_login_via_frappe_foreign_data_denied(self):
		self.assert_gate_denies("login_via_frappe", signed_in=True)

	def test_login_via_office365_guest_denied(self):
		self.assert_gate_denies("login_via_office365")

	def test_login_via_office365_foreign_data_denied(self):
		self.assert_gate_denies("login_via_office365", signed_in=True)

	def test_login_via_salesforce_guest_denied(self):
		self.assert_gate_denies("login_via_salesforce")

	def test_login_via_salesforce_foreign_data_denied(self):
		self.assert_gate_denies("login_via_salesforce", signed_in=True)

	def test_login_via_fairlogin_guest_denied(self):
		self.assert_gate_denies("login_via_fairlogin")

	def test_login_via_fairlogin_foreign_data_denied(self):
		self.assert_gate_denies("login_via_fairlogin", signed_in=True)

	def test_login_via_keycloak_guest_denied(self):
		self.assert_gate_denies("login_via_keycloak")

	def test_login_via_keycloak_foreign_data_denied(self):
		self.assert_gate_denies("login_via_keycloak", signed_in=True)

	def test_custom_guest_denied(self):
		self.assert_gate_denies("custom")

	def test_custom_foreign_data_denied(self):
		self.assert_gate_denies("custom", signed_in=True)

	def test_ldap_login_guest_denied(self):
		self.assert_gate_denies("ldap_login")

	def test_ldap_login_foreign_data_denied(self):
		self.assert_gate_denies("ldap_login", signed_in=True)
