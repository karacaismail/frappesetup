"""Tests of the “Social Login Key” setup step (task document, checkpoint 1, item 3; V-7)."""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.exceptions import KeycloakSettingsMissing
from platform_core.kimlik.tests import helpers as h


class TestSetup(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.patcher = h.jwks_patch()
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def test_custom_record_with_the_same_name_is_reused(self):
		frappe.delete_doc(
			"Social Login Key", "keycloak", force=True, ignore_permissions=True, ignore_missing=True
		)
		custom = frappe.new_doc("Social Login Key")
		custom.update(
			{
				"provider_name": "Keycloak",
				"social_login_provider": "Custom",
				"authorize_url": "x",
				"access_token_url": "y",
				"redirect_url": "z",
			}
		)
		custom.insert()
		result = provider_setup.ensure_social_login_key()
		self.assertEqual(result["social_login_key"], "keycloak")
		self.assertEqual(frappe.db.get_value("Social Login Key", "keycloak", "user_id_property"), "sub")

	def test_running_twice_keeps_one_record_with_expected_fields(self):
		first = provider_setup.ensure_social_login_key()
		second = provider_setup.ensure_social_login_key()
		self.assertEqual(first, second)
		self.assertEqual(first["social_login_key"], "keycloak")
		self.assertEqual(frappe.db.count("Social Login Key", {"social_login_provider": "Keycloak"}), 1)
		doc = frappe.get_doc("Social Login Key", "keycloak")
		self.assertEqual(doc.user_id_property, "sub")
		self.assertEqual(doc.sign_ups, "Deny")
		self.assertEqual(doc.provider_name, "Atonota")
		# Frappe's own button would send a state this app does not know, so the key stays disabled.
		self.assertEqual(doc.enable_social_login, 0)
		self.assertEqual(doc.custom_base_url, 1)
		self.assertEqual(doc.base_url, "http://kimlik.localhost:8660/realms/platform")
		self.assertEqual(doc.authorize_url, "/protocol/openid-connect/auth")
		self.assertEqual(doc.access_token_url, "/protocol/openid-connect/token")
		self.assertEqual(doc.api_endpoint, "/protocol/openid-connect/userinfo")
		self.assertEqual(doc.redirect_url, "/api/method/platform_core.api.auth.keycloak_callback")
		self.assertEqual(doc.client_id, "site-kiraci1")
		self.assertEqual(frappe.parse_json(doc.auth_url_data), {"response_type": "code", "scope": "openid"})
		self.assertEqual(doc.get_password("client_secret"), "test-client-secret-fake")

	def test_display_name_follows_brand_setting(self):
		provider_setup.ensure_social_login_key()
		with h.SiteSettings({"kimlik_marka_adi": "Deneme Marka"}):
			provider_setup.ensure_social_login_key()
			self.assertEqual(
				frappe.db.get_value("Social Login Key", "keycloak", "provider_name"), "Deneme Marka"
			)
		provider_setup.ensure_social_login_key()
		self.assertEqual(frappe.db.get_value("Social Login Key", "keycloak", "provider_name"), "Atonota")

	def test_missing_setting_raises_clear_error(self):
		with h.SiteSettings({"keycloak_client_secret": ""}), self.assertRaises(KeycloakSettingsMissing):
			provider_setup.ensure_social_login_key()

	def test_setup_endpoint_is_system_manager_only(self):
		h.refresh()
		endpoint = "/api/method/platform_core.api.auth.setup_keycloak_login"
		guest = h.request(h.new_client().post, endpoint)
		self.assertEqual(guest.status_code, 403)

		end_user = h.new_client()
		provider_setup.ensure_social_login_key()
		h.refresh()
		h.login_with_keycloak(end_user, h.userinfo("sub-ayse", h.AYSE))
		self.addCleanup(h.clear_links)
		self.assertEqual(h.logged_user(end_user), h.AYSE)
		response = h.request(end_user.post, endpoint, headers=h.csrf_headers(end_user))
		self.assertEqual(response.status_code, 403)

		admin = h.new_client()
		admin.set_cookie("sid", self.sid)
		response = h.request(admin.post, endpoint, headers=h.csrf_headers(admin))
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"]["social_login_key"], "keycloak")
