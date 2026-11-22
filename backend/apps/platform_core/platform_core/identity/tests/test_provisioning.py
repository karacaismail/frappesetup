"""Tests of the user provisioning endpoints. Expected behaviour: docs/sozlesmeler.md section 5, D-5, G-16.

- `provision` returns the same result when the same request arrives twice,
- the created user is a “Website User” without desk roles,
- an unverified e-mail does not create the first link,
- an end user cannot open the desk.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import anonymization, provider_setup
from platform_core.identity.tests import helpers as h

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
		cls.key = h.key()
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
		self.assertEqual(frappe.db.count("PLT Identity Link", {"issuer": h.ISSUER, "subject": "sub-new"}), 1)
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

	def test_provision_does_not_adopt_a_system_user(self):
		# A desk account must never be taken over by end-user provisioning (O3 in the security review).
		admin = h.ensure_user("ops.kisi@example.test", user_type="System User", roles=["System Manager"])
		h.refresh()
		self.addCleanup(
			lambda: (frappe.delete_doc("User", admin, force=True, ignore_permissions=True), h.refresh())
		)
		response = self.call(PROVISION, provision_body(email=admin, subject="sub-ops"))
		self.assertEqual(response.status_code, 409, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "IdentityConflict")
		h.refresh()
		self.assertFalse(frappe.db.exists("PLT Identity Link", {"issuer": h.ISSUER, "subject": "sub-ops"}))
		self.assertEqual(frappe.db.get_value("User", admin, "user_type"), "System User")

	def test_provision_requires_email_verified_and_text_names(self):
		body = provision_body()
		body.pop("email_verified")
		response = self.call(PROVISION, body)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")
		response = self.call(PROVISION, provision_body(first_name=123))
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")
		response = self.call(PROVISION, provision_body(enabled="yes"))
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")

	def test_subject_and_issuer_lengths_follow_storage(self):
		# DocType lengths: subject 140, issuer 255 (K2 in the security review).
		ok = self.call(PROVISION, provision_body(subject="s" * 140))
		self.assertEqual(ok.status_code, 200, ok.data[:300])
		too_long = self.call(PROVISION, provision_body(subject="s" * 141, email=NEW_2))
		self.assertEqual(too_long.status_code, 400)
		self.assertEqual(too_long.json.get("exc_type"), "InvalidInput")

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
			frappe.db.get_value("PLT Identity Link", {"issuer": h.ISSUER, "subject": "sub-new"}, "user"),
			NEW_2,
		)
		second = self.call(CHANGE_EMAIL, body)
		self.assertEqual(first.json["message"], second.json["message"])
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-new", NEW_2))
		self.assertEqual(h.logged_user(client), NEW_2)

	def test_change_email_after_disabling_user_is_repeatable(self):
		created = self.call(PROVISION, provision_body())
		self.assertEqual(created.status_code, 200, created.data[:300])
		identity = {"issuer": h.ISSUER, "subject": "sub-new"}
		disabled = self.call(SET_ENABLED, {**identity, "enabled": False})
		self.assertEqual(disabled.status_code, 200, disabled.data[:300])
		self.assertEqual(disabled.json["message"], {"user": NEW, "enabled": False})

		body = {**identity, "new_email": NEW_2}
		for _attempt in range(2):
			response = self.call(CHANGE_EMAIL, body)
			self.assertEqual(response.status_code, 200, response.data[:300])
			self.assertEqual(response.json["message"], {"user": NEW_2})
		h.refresh()
		self.assertFalse(frappe.db.exists("User", NEW))
		self.assertEqual(frappe.db.get_value("User", NEW_2, "enabled"), 0)

	def test_change_email_uses_the_same_lock_order_as_frappe(self):
		created = self.call(PROVISION, provision_body())
		self.assertEqual(created.status_code, 200, created.data[:300])
		identity = {"issuer": h.ISSUER, "subject": "sub-new"}
		disabled = self.call(SET_ENABLED, {**identity, "enabled": False})
		self.assertEqual(disabled.status_code, 200, disabled.data[:300])

		site = frappe.local.site
		user_locked = Event()
		rename_needs_user = Event()
		database = type(frappe.local.db)
		query = database.sql

		def observe_user_lock(connection, statement, *args, **kwargs):
			request = getattr(frappe.local, "request", None)
			sql = str(statement).upper()
			if (
				request
				and request.path == CHANGE_EMAIL
				and "`TABUSER`" in sql
				and (sql.startswith("UPDATE ") or "FOR UPDATE" in sql)
			):
				rename_needs_user.set()
			return query(connection, statement, *args, **kwargs)

		def lock_user_then_link():
			frappe.init(site=site)
			frappe.connect()
			try:
				# Frappe renames the User row before updating the fields that link to it.
				frappe.db.get_value("User", NEW, "name", for_update=True)
				user_locked.set()
				if not rename_needs_user.wait(timeout=15):
					raise AssertionError("The e-mail request did not try to lock the User row.")
				frappe.db.get_value("PLT Identity Link", identity, "name", for_update=True)
			finally:
				frappe.db.rollback()
				frappe.destroy()

		body = {**identity, "new_email": NEW_2}
		with ThreadPoolExecutor(max_workers=1) as executor:
			worker = executor.submit(lock_user_then_link)
			self.assertTrue(user_locked.wait(timeout=15))
			with patch.object(database, "sql", observe_user_lock):
				response = self.call(CHANGE_EMAIL, body)
			self.assertEqual(response.status_code, 200, response.data[:300])
			worker.result(timeout=15)

		self.assertEqual(response.json["message"], {"user": NEW_2})
		repeated = self.call(CHANGE_EMAIL, body)
		self.assertEqual(repeated.status_code, 200, repeated.data[:300])
		self.assertEqual(response.json["message"], repeated.json["message"])

	def test_identity_writes_retry_when_the_locked_link_changes(self):
		identity = {"issuer": h.ISSUER, "subject": "sub-new"}
		lock_identity = anonymization.lock_identity
		for endpoint, body, expected in (
			(
				PROVISION,
				provision_body(),
				{"user": NEW, "enabled": True, "linked": True, "user_type": "Website User"},
			),
			(SET_ENABLED, {**identity, "enabled": False}, {"user": NEW, "enabled": False}),
			(CHANGE_EMAIL, {**identity, "new_email": NEW_2}, {"user": NEW_2}),
		):
			with self.subTest(endpoint=endpoint):

				def fail_once(*args, **kwargs):
					if locking.call_count == 1:
						raise frappe.QueryDeadlockError("Test concurrent link change")
					return lock_identity(*args, **kwargs)

				with patch.object(anonymization, "lock_identity", side_effect=fail_once) as locking:
					response = self.call(endpoint, body)
				self.assertEqual(response.status_code, 200, response.data[:200])
				self.assertEqual(response.json["message"], expected)
				self.assertEqual(locking.call_count, 2)

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
