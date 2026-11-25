"""Exercise the identity endpoints over Frappe RPC.

The reconciliation and identity-sync endpoints follow contract section 7. The user management
endpoints of the panel (G-98) have their behavior tests in `identity/tests/test_user_admin.py`.
"""

from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase
from frappe.utils import get_test_client

from platform_core.identity.tests import helpers as h
from platform_core.identity.tests import test_user_admin as ua

ENDPOINT = "/api/method/platform_core.api.identity.list_identities"
DISABLED_USER = "reconciliation.disabled@example.test"


class TestListIdentities(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = h.SiteSettings()
		settings.__enter__()
		cls.addClassCleanup(settings.__exit__, None, None, None)
		h.clear_links(DISABLED_USER)
		cls.addClassCleanup(h.clear_links, DISABLED_USER)
		h.ensure_user(h.AYSE)
		h.ensure_user(DISABLED_USER)
		frappe.db.set_value("User", DISABLED_USER, "enabled", 0)
		h.make_link("reconciliation-z", h.AYSE)
		h.make_link("reconciliation-a", DISABLED_USER)
		cls.key = h.key()
		patcher = h.jwks_patch(cls.key)
		patcher.start()
		cls.addClassCleanup(patcher.stop)

	def call(self, *, params=None, claims=None, client=None, with_token=True):
		token = self.key.sign(h.access_payload(**(claims or {}))) if with_token else None
		headers = {"Authorization": f"Bearer {token}"} if token else {}
		return h.request((client or h.new_client()).get, ENDPOINT, query_string=params, headers=headers)

	def page(self, **params):
		response = self.call(params=params)
		self.assertEqual(response.status_code, 200, response.data[:400])
		return response.json["message"]

	def test_orders_and_paginates_with_only_the_contract_fields(self):
		first = {"issuer": h.ISSUER, "subject": "reconciliation-a", "enabled": False}
		second = {"issuer": h.ISSUER, "subject": "reconciliation-z", "enabled": True}
		self.assertEqual(self.page(), {"identities": [first, second], "has_next_page": False})
		self.assertEqual(self.page(page_length=1), {"identities": [first], "has_next_page": True})
		self.assertEqual(self.page(start=1, page_length=1), {"identities": [second], "has_next_page": False})
		self.assertEqual(self.page(start=2), {"identities": [], "has_next_page": False})

	def test_refuses_invalid_query_parameters(self):
		for params in (
			{"start": -1},
			{"start": "1.5"},
			{"page_length": 0},
			{"page_length": 501},
			{"user": h.AYSE},
		):
			with self.subTest(params=params):
				response = self.call(params=params)
				self.assertEqual(response.status_code, 400, response.data[:300])
				self.assertEqual(response.json["exc_type"], "InvalidInput")

	def test_list_identities_requires_frappe_read_permission(self):
		check = frappe.has_permission

		def deny_identity_links(doctype, *args, **kwargs):
			return False if doctype == "PLT Identity Link" else check(doctype, *args, **kwargs)

		with patch.object(frappe, "has_permission", side_effect=deny_identity_links):
			response = self.call()
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertNotIn("message", response.json)

	def test_list_identities_guest_denied(self):
		response = self.call(with_token=False)
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertNotIn("message", response.json)

	def test_list_identities_foreign_data_denied(self):
		admin = h.new_client()
		admin.set_cookie("sid", self.sid)
		with h.SiteSettings({"identity_service_azp": ["identity-sync", "another-service"]}):
			for response, status in (
				(self.call(with_token=False, client=admin), 403),
				(self.call(claims={"azp": "mobile"}), 401),
				(self.call(claims={"azp": "another-service"}), 403),
				(self.call(claims={"aud": "other-tenant"}), 401),
				(self.call(client=admin), 401),
			):
				self.assertEqual(response.status_code, status, response.data[:300])
				self.assertNotIn("message", response.json)

	def _assert_mutation_denied(self, method, *, claims=None):
		headers = {}
		if claims:
			headers["Authorization"] = f"Bearer {self.key.sign(h.access_payload(**claims))}"
		response = h.request(
			h.new_client().post,
			f"/api/method/platform_core.api.identity.{method}",
			json={"issuer": h.ISSUER, "subject": "reconciliation-z"},
			headers=headers,
		)
		self.assertEqual(response.status_code, 401 if claims else 403)
		self.assertNotIn("message", response.json)

	def test_provision_guest_denied(self):
		self._assert_mutation_denied("provision")

	def test_provision_foreign_data_denied(self):
		self._assert_mutation_denied("provision", claims={"aud": "other-tenant"})

	def test_set_enabled_guest_denied(self):
		self._assert_mutation_denied("set_enabled")

	def test_set_enabled_foreign_data_denied(self):
		self._assert_mutation_denied("set_enabled", claims={"aud": "other-tenant"})

	def test_change_email_guest_denied(self):
		self._assert_mutation_denied("change_email")

	def test_change_email_foreign_data_denied(self):
		self._assert_mutation_denied("change_email", claims={"aud": "other-tenant"})

	def test_anonymize_user_guest_denied(self):
		self._assert_mutation_denied("anonymize_user")

	def test_anonymize_user_foreign_data_denied(self):
		self._assert_mutation_denied("anonymize_user", claims={"aud": "other-tenant"})


class TestUserAdminEndpoints(ua.TenantUsersCase):
	"""G-98: the two endpoints of the panel refuse a guest and data outside the tenant (AJA-890)."""

	def guest(self):
		return get_test_client(use_cookies=True)

	def test_set_user_role_profiles_guest_denied(self):
		response = self.assign(self.guest(), ua.MEMBER, [ua.PROFILE])

		self.assertEqual(response.status_code, 403)
		self.assertNotIn("message", response.json)
		self.assertNotIn(ua.PLAIN_ROLE, frappe.get_roles(ua.MEMBER))

	def test_set_user_role_profiles_foreign_data_denied(self):
		"""A user of another tenant is not changed. A plain user changes nobody, not even itself."""
		for client, user in ((self.login(), ua.STRANGER), (self.login(ua.MEMBER), ua.MEMBER)):
			with self.subTest(user=user):
				response = self.assign(client, user, [ua.PROFILE])

				self.assertEqual(response.status_code, 403)
				self.assertNotIn("message", response.json)
				self.assertNotIn(ua.PLAIN_ROLE, frappe.get_roles(user))

	def test_invite_user_guest_denied(self):
		fake = self.serve(ua.FakeIdentitySync())

		response = self.invite(self.guest(), dry_run=True)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn("message", response.json)
		self.assertEqual(fake.calls, [])

	def test_invite_user_foreign_data_denied(self):
		"""Nobody invites into another organization. A plain user invites nobody."""
		fake = self.serve(ua.FakeIdentitySync())

		other_organization = self.invite(self.login(), dry_run=True, organization_id="org-other")
		plain_user = self.invite(self.login(ua.MEMBER), dry_run=True)

		self.assertEqual(other_organization.status_code, 400)
		self.assertEqual(plain_user.status_code, 403)
		self.assertNotIn("message", plain_user.json)
		self.assertEqual(fake.calls, [])
