"""Tests of the user provisioning endpoints. Expected behaviour: docs/sozlesmeler.md section 5, D-5, G-16.

- `provision` returns the same result when the same request arrives twice,
- the created user is a “Website User” without desk roles,
- an unverified e-mail does not create the first link,
- an end user cannot open the desk.
"""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

PROVISION = "/api/method/platform_core.api.identity.provision"
SET_ENABLED = "/api/method/platform_core.api.identity.set_enabled"
CHANGE_EMAIL = "/api/method/platform_core.api.identity.change_email"
NEW = "yeni.kisi@example.test"
NEW_2 = "yeni.kisi.2@example.test"


def provision_body(**overrides) -> dict:
	body = {
		"issuer": h.ISSUER,
		"subject": "sub-new",
		"email": NEW,
		"email_verified": True,
		"first_name": "Yeni",
		"last_name": "Kisi",
		"enabled": True,
		"role_profiles": [],
	}
	body.update(overrides)
	return body


class TestIdentityEndpoints(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		cls.desk_profile = h.ensure_role_profile("Kimlik Test Desk", ["System Manager"])
		cls.portal_role = h.ensure_role("Kimlik Test Portal Role", desk_access=0)
		cls.portal_profile = h.ensure_role_profile("Kimlik Test Portal", [cls.portal_role])
		h.refresh()
		cls.key = h.Key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	@classmethod
	def tearDownClass(cls):
		h.clear_links()
		for email in (NEW, NEW_2):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
		h.refresh()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links(NEW, NEW_2)
		for email in (NEW, NEW_2):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
		h.refresh()

	def call(self, path, body):
		token = self.key.sign(h.access_payload())
		return h.request(h.new_client().post, path, json=body, headers={"Authorization": f"Bearer {token}"})

	def test_provision_creates_user_and_is_repeatable(self):
		first = self.call(PROVISION, provision_body())
		self.assertEqual(first.status_code, 200, first.data[:300])
		second = self.call(PROVISION, provision_body())
		self.assertEqual(second.status_code, 200)
		self.assertEqual(first.json["message"], second.json["message"])
		self.assertEqual(
			first.json["message"], {"user": NEW, "enabled": True, "linked": True, "user_type": "Website User"}
		)
		h.refresh()
		user = frappe.get_doc("User", NEW)
		self.assertEqual(user.user_type, "Website User")
		self.assertEqual(user.first_name, "Yeni")
		self.assertEqual([r.role for r in user.roles if r.role not in frappe.permissions.AUTOMATIC_ROLES], [])
		self.assertEqual(
			frappe.db.count("Platform Identity Link", {"issuer": h.ISSUER, "subject": "sub-new"}), 1
		)
		self.assertEqual(frappe.db.count("Email Queue", {"reference_name": NEW}), 0)

	def test_provision_unverified_email_creates_no_link(self):
		response = self.call(PROVISION, provision_body(email_verified=False))
		self.assertEqual(response.status_code, 409)
		self.assertEqual(response.json.get("exc_type"), "EmailNotVerified")
		h.refresh()
		self.assertFalse(frappe.db.exists("User", NEW))

	def test_provision_existing_link_needs_no_verification(self):
		self.call(PROVISION, provision_body())
		response = self.call(PROVISION, provision_body(email_verified=False, first_name="Guncel"))
		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		self.assertEqual(frappe.db.get_value("User", NEW, "first_name"), "Guncel")

	def test_provision_rejects_desk_role(self):
		response = self.call(PROVISION, provision_body(role_profiles=[self.desk_profile]))
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "DeskRoleNotAllowed")
		h.refresh()
		self.assertFalse(frappe.db.exists("User", NEW))

	def test_provision_assigns_portal_role_profile(self):
		response = self.call(PROVISION, provision_body(role_profiles=[self.portal_profile]))
		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		user = frappe.get_doc("User", NEW)
		self.assertEqual([r.role_profile for r in user.role_profiles], [self.portal_profile])
		self.assertIn(self.portal_role, [r.role for r in user.roles])
		self.assertEqual(user.user_type, "Website User")

	def test_provision_same_email_different_sub_conflicts(self):
		self.call(PROVISION, provision_body())
		response = self.call(PROVISION, provision_body(subject="sub-other"))
		self.assertEqual(response.status_code, 409)
		self.assertEqual(response.json.get("exc_type"), "IdentityConflict")

	def test_provision_email_mismatch_is_409(self):
		self.call(PROVISION, provision_body())
		response = self.call(PROVISION, provision_body(email=NEW_2))
		self.assertEqual(response.status_code, 409)
		self.assertEqual(response.json.get("exc_type"), "EmailMismatch")

	def test_provision_foreign_issuer_is_rejected(self):
		response = self.call(PROVISION, provision_body(issuer="http://attacker.example/realms/platform"))
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "UnknownIssuer")

	def test_provision_missing_field_is_400(self):
		response = self.call(PROVISION, {"issuer": h.ISSUER, "subject": "sub-new"})
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")

	def test_set_enabled_disables_closes_sessions_and_is_repeatable(self):
		self.call(PROVISION, provision_body())
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-new", NEW))
		self.assertEqual(h.logged_user(client), NEW)
		body = {"issuer": h.ISSUER, "subject": "sub-new", "enabled": False}
		first = self.call(SET_ENABLED, body)
		self.assertEqual(first.status_code, 200, first.data[:300])
		self.assertEqual(first.json["message"], {"user": NEW, "enabled": False})
		self.assertEqual(h.logged_user(client), "Guest")
		again = h.login_with_keycloak(h.new_client(), h.userinfo("sub-new", NEW))
		self.assertNotEqual(again.status_code, 302)
		second = self.call(SET_ENABLED, body)
		self.assertEqual(first.json["message"], second.json["message"])
		enabled = self.call(SET_ENABLED, {**body, "enabled": True})
		self.assertEqual(enabled.json["message"], {"user": NEW, "enabled": True})

	def test_set_enabled_unknown_identity_is_404(self):
		response = self.call(SET_ENABLED, {"issuer": h.ISSUER, "subject": "sub-missing", "enabled": True})
		self.assertEqual(response.status_code, 404)
		self.assertEqual(response.json.get("exc_type"), "IdentityNotFound")

	def test_change_email_renames_user_and_keeps_link(self):
		self.call(PROVISION, provision_body())
		body = {"issuer": h.ISSUER, "subject": "sub-new", "new_email": NEW_2}
		first = self.call(CHANGE_EMAIL, body)
		self.assertEqual(first.status_code, 200, first.data[:300])
		self.assertEqual(first.json["message"], {"user": NEW_2})
		h.refresh()
		self.assertFalse(frappe.db.exists("User", NEW))
		self.assertEqual(frappe.db.get_value("User", NEW_2, "email"), NEW_2)
		self.assertEqual(
			frappe.db.get_value("Platform Identity Link", {"issuer": h.ISSUER, "subject": "sub-new"}, "user"),
			NEW_2,
		)
		second = self.call(CHANGE_EMAIL, body)
		self.assertEqual(first.json["message"], second.json["message"])
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-new", NEW_2))
		self.assertEqual(h.logged_user(client), NEW_2)

	def test_change_email_to_used_address_is_409(self):
		self.call(PROVISION, provision_body())
		response = self.call(CHANGE_EMAIL, {"issuer": h.ISSUER, "subject": "sub-new", "new_email": h.AYSE})
		self.assertEqual(response.status_code, 409)
		self.assertEqual(response.json.get("exc_type"), "EmailInUse")

	def test_end_user_cannot_open_desk(self):
		self.call(PROVISION, provision_body())
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-new", NEW))
		self.assertEqual(h.logged_user(client), NEW)
		for path in ("/desk", "/app"):
			response = h.request(client.get, path, follow_redirects=True)
			self.assertEqual(response.status_code, 403, f"{path}: {response.status_code}")
