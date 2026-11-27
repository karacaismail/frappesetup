"""Panel role “Tenant Admin Assistant” (G-168, AJA-831). Written before the code (D-2).

The tenant admin gives this role to a person of the own company. The person is a Website User.
The person sees the site and its state. The person cannot change roles or permissions: the G-62
endpoints refuse the person. The person cannot create or delete users and cannot change the plan.

The lists below say what the panel shows. The panel test
`tests/e2e/rol-tenant-admin-assistant.spec.ts` checks them.
"""

# The panel texts are Turkish. Their dotless i letters are intended.
# ruff: noqa: RUF001

import unittest

from platform_core.access.tests import panel_roles
from platform_core.access.tests.panel_roles import ACCESS_API, RESELLER_API, frappe

ROLE = panel_roles.TENANT_ADMIN_ASSISTANT
USER = "pr.kiraci.yardimci@example.test"
OTHER_USER = "pr.kiraci.calisan@example.test"

# Menu groups the role sees (G-168). “Yönetim” shows only the user list.
MENU = ("Hesap", "Yönetim", "İzin talepleri", "Site ve plan", "Yapay zekâ işlemleri")
MENU_HIDDEN = ("Yapay zekâ sağlayıcıları", "Müşteriler")
# Pages the role opens and pages it cannot open.
PAGES_OPEN = ("/account", "/administration", "/hr", "/site-plan", "/ai-operations")
PAGES_CLOSED = ("/administration/ai-providers", "/customers")
# Action buttons. “Site ve plan” is read only. “Yönetim” has no role and access sections.
BUTTONS_SHOWN = ()
BUTTONS_HIDDEN = (
	"Erişimi açıkla",
	"Yeni kullanıcı",
	"Kullanıcıyı sil",
	"Planı değiştir",
	"Siteyi sil",
	"Siteyi devret",
	"Yedekten geri yükle",
	"Yeni müşteri isteği",
)
# API requests the role is refused (HTTP 403).
DENIED = (
	"GET platform_core.api.access.list_role_permissions",
	"POST platform_core.api.access.set_role_permission",
	"POST platform_core.api.access.remove_role_permission",
	"POST Role",
	"POST User",
	"PUT User/<other user> roles",
	"PUT User/<self> roles (no role is gained)",
	"DELETE User/<other user>",
	"GET platform_core.api.reseller.list_customers",
	"POST platform_core.api.reseller.request_customer",
	"POST platform_core.api.reseller.approve_customer_request",
	"POST Reseller Customer Link",
)


class TestTenantAdminAssistantFixture(panel_roles.RoleFixtureContract, unittest.TestCase):
	ROLE = ROLE


class TestTenantAdminAssistantHttp(panel_roles.PanelRoleHttpCase):
	ROLE = ROLE
	USER = USER
	FORBIDDEN_ROLES = (
		panel_roles.TENANT_ADMIN,
		panel_roles.PLATFORM_OPERATOR,
		panel_roles.RESELLER_ADMIN,
		panel_roles.RESELLER_ASSISTANT,
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# A plain colleague. The assistant must not change or delete this account.
		if not frappe.db.exists("User", OTHER_USER):
			frappe.get_doc(
				doctype="User", email=OTHER_USER, first_name="pr.kiraci.calisan", send_welcome_email=0
			).insert(ignore_permissions=True)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		if frappe.db.exists("User", OTHER_USER):
			frappe.delete_doc("User", OTHER_USER, force=True, ignore_permissions=True)
		super().tearDownClass()

	def test_assistant_reads_the_user_list(self):
		"""Positive case (G-168): “Yönetim” shows the user list to the assistant."""
		response = self.send(self.login(), "GET", panel_roles.REST + "User")

		self.assertEqual(response.status_code, 200, response.data[:300])

	def test_assistant_is_refused_by_the_g62_endpoints(self):
		client = self.login()

		self.assert_denied(client, "GET", ACCESS_API + "list_role_permissions", doctype="ToDo")
		self.assert_denied(
			client,
			"POST",
			ACCESS_API + "set_role_permission",
			doctype="ToDo",
			role=ROLE,
			permissions={"read": 1},
		)
		self.assert_denied(client, "POST", ACCESS_API + "remove_role_permission", doctype="ToDo", role=ROLE)

	def test_assistant_cannot_create_a_role(self):
		self.assert_rest_denied(
			self.login(), "POST", "Role", body={"role_name": "PR Yeni Rol", "desk_access": 0}
		)

		self.assertFalse(frappe.db.exists("Role", "PR Yeni Rol"))

	def test_assistant_cannot_create_change_or_delete_a_user(self):
		client = self.login()

		self.assert_rest_denied(
			client, "POST", "User", body={"email": "pr.yeni@example.test", "first_name": "pr.yeni"}
		)
		self.assert_rest_denied(
			client, "PUT", "User", OTHER_USER, body={"roles": [{"role": panel_roles.TENANT_ADMIN}]}
		)
		self.assert_rest_denied(client, "DELETE", "User", OTHER_USER)

		self.assertFalse(frappe.db.exists("User", "pr.yeni@example.test"))
		self.assertTrue(frappe.db.exists("User", OTHER_USER))
		self.assertNotIn(panel_roles.TENANT_ADMIN, frappe.get_roles(OTHER_USER))

	def test_assistant_cannot_give_itself_the_admin_role(self):
		"""Frappe may refuse the change or drop the roles field. Either way no role is gained."""
		response = self.send(
			self.login(),
			"PUT",
			panel_roles.REST + f"User/{USER}",
			body={"roles": [{"role": panel_roles.TENANT_ADMIN}]},
		)

		self.assertIn(response.status_code, (200, 403, 417), response.data[:300])
		frappe.clear_cache(user=USER)
		self.assertNotIn(panel_roles.TENANT_ADMIN, frappe.get_roles(USER))
		self.assertIn(ROLE, frappe.get_roles(USER))

	def test_assistant_is_refused_by_the_reseller_endpoints(self):
		client = self.login()

		self.assert_denied(client, "GET", RESELLER_API + "list_customers")
		self.assert_denied(
			client,
			"POST",
			RESELLER_API + "request_customer",
			customer_name="Örnek Müşteri",
			contact_email="ornek.musteri@example.test",
		)

	# --- AI provider types (AJA-947) ---

	def test_assistant_cannot_read_the_schema_of_the_ai_types(self):
		client = self.login()
		for doctype in panel_roles.AI_TYPES:
			with self.subTest(doctype=doctype):
				response = self.call(client, "GET", panel_roles.META_API, doctype=doctype)
				self.assertEqual(response.status_code, 403, (doctype, response.data[:300]))

	def test_assistant_cannot_read_or_change_the_ai_records(self):
		records = self.make_ai_records()
		client = self.login()
		for doctype, name in records.items():
			with self.subTest(doctype=doctype):
				response = self.send(client, "GET", panel_roles.REST + f"{doctype}/{name}")
				self.assertEqual(response.status_code, 403, (doctype, response.data[:300]))
				self.assertNotIn(panel_roles.FAKE_AI_KEY.encode(), response.data)
				self.assert_rest_denied(client, "DELETE", doctype, name)
				self.assertTrue(frappe.db.exists(doctype, name))
