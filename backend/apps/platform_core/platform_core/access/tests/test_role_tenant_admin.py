"""Panel role “Tenant Admin” (G-62, AJA-831). Written before the code (D-2).

The tenant admin manages the roles and permissions of its own site. The admin is a Website User.
The admin can never give, change or use the “System Manager” and “Administrator” roles.
The admin is no reseller: the reseller endpoints refuse the admin.

The lists below say what the panel shows. The panel test `tests/e2e/rol-tenant-admin.spec.ts` checks them.
"""

# The panel texts are Turkish. Their dotless i letters are intended.
# ruff: noqa: RUF001

import unittest

from platform_core.access.tests import panel_roles
from platform_core.access.tests.panel_roles import ACCESS_API, LINK_DOCTYPE, RESELLER_API, frappe

ROLE = panel_roles.TENANT_ADMIN
USER = "pr.kiraci.yonetici@example.test"

# Menu groups the role sees. Every group of today's panel. No “Müşteriler” group.
MENU = ("Hesap", "Yönetim", "İzin talepleri", "Site ve plan", "Yapay zekâ işlemleri")
# Pages the role opens and pages it cannot open.
PAGES_OPEN = (
	"/account",
	"/administration",
	"/administration/ai-providers",
	"/hr",
	"/site-plan",
	"/ai-operations",
)
PAGES_CLOSED = ("/customers",)
# Action buttons the role sees and does not see.
BUTTONS_SHOWN = ("Erişimi açıkla",)
BUTTONS_HIDDEN = ("Yeni müşteri isteği",)
# API requests the role is refused (HTTP 403).
DENIED = (
	"PUT Role/System Manager",
	"DELETE Role/Administrator",
	"POST platform_core.api.access.set_role_permission (System Manager)",
	"POST platform_core.api.access.remove_role_permission (System Manager)",
	"GET platform_core.api.reseller.list_customers",
	"GET platform_core.api.reseller.customer_status",
	"POST platform_core.api.reseller.request_customer",
	"POST platform_core.api.reseller.approve_customer_request",
	"POST Reseller Customer Link",
)


class TestTenantAdminFixture(panel_roles.RoleFixtureContract, unittest.TestCase):
	ROLE = ROLE


class TestTenantAdminHttp(panel_roles.PanelRoleHttpCase):
	ROLE = ROLE
	USER = USER
	FORBIDDEN_ROLES = (
		panel_roles.PLATFORM_OPERATOR,
		panel_roles.TENANT_ADMIN_ASSISTANT,
		panel_roles.RESELLER_ADMIN,
		panel_roles.RESELLER_ASSISTANT,
	)

	def test_admin_reads_the_permission_rows_of_a_type(self):
		"""Positive case: the G-62 endpoint exists and serves the admin.

		The type is a business type. Framework types such as "ToDo" stay closed to the admin (G-62).
		"""
		response = self.call(
			self.login(), "GET", ACCESS_API + "list_role_permissions", doctype="Sales Partner Type"
		)

		self.assertEqual(response.status_code, 200, response.data[:300])

	def test_admin_cannot_change_or_delete_a_protected_role(self):
		client = self.login()

		self.assert_rest_denied(client, "PUT", "Role", "System Manager", body={"desk_access": 0})
		self.assert_rest_denied(client, "DELETE", "Role", "Administrator")

		self.assertEqual(frappe.db.get_value("Role", "System Manager", "desk_access"), 1)

	def test_admin_cannot_give_or_take_permission_rows_of_system_manager(self):
		client = self.login()

		self.assert_denied(
			client,
			"POST",
			ACCESS_API + "set_role_permission",
			doctype="ToDo",
			role="System Manager",
			permissions={"read": 1},
		)
		self.assert_denied(
			client, "POST", ACCESS_API + "remove_role_permission", doctype="ToDo", role="System Manager"
		)

	def test_admin_is_refused_by_the_reseller_endpoints(self):
		client = self.login()
		self.assert_denied(client, "GET", RESELLER_API + "list_customers")
		self.assert_denied(
			client, "GET", RESELLER_API + "customer_status", customer_tenant=panel_roles.OTHER_CUSTOMER
		)
		self.assert_denied(
			client,
			"POST",
			RESELLER_API + "request_customer",
			customer_name="Örnek Müşteri",
			contact_email="ornek.musteri@example.test",
		)
		self.assertFalse(frappe.db.exists(LINK_DOCTYPE, {"customer_tenant": "yeni-musteri.example.test"}))
