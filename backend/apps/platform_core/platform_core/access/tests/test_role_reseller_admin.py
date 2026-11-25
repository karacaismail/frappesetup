"""Panel role “Reseller Admin” (G-169, AJA-831). Written before the code (D-2).

A reseller sells the platform to customers. The platform operator gives this role to the person in
charge of an approved reseller. The role lives on the reseller's own tenant. The admin sees the own
customers and their site state. The admin sends a request for a new customer tenant.

The lists below say what the panel shows. The panel test
`tests/e2e/rol-reseller-admin.spec.ts` checks them.
"""

# The panel texts are Turkish. Their dotless i letters are intended.
# ruff: noqa: RUF001

import unittest

from platform_core.access.tests import panel_roles, reseller_checks
from platform_core.access.tests.panel_roles import REQUEST_DOCTYPE, RESELLER_API, frappe

ROLE = panel_roles.RESELLER_ADMIN
USER = "pr.bayi.yonetici@example.test"

# Menu groups the role sees (G-169).
MENU = ("Hesap", "Site ve plan", "Müşteriler")
MENU_HIDDEN = ("Yönetim", "İzin talepleri", "Yapay zekâ işlemleri", "Yapay zekâ sağlayıcıları")
# Pages the role opens and pages it cannot open.
PAGES_OPEN = ("/account", "/site-plan", "/customers")
PAGES_CLOSED = ("/administration", "/administration/ai-providers", "/hr", "/ai-operations")
# Action buttons the role sees and does not see.
BUTTONS_SHOWN = ("Yeni müşteri isteği",)
BUTTONS_HIDDEN = ("Erişimi açıkla",)
# API requests the role is refused (HTTP 403, business data 403 or 404).
DENIED = (
	"GET platform_core.api.reseller.customer_status (customer of another reseller)",
	"GET platform_core.api.reseller.customer_status (unknown customer)",
	"POST platform_core.api.reseller.approve_customer_request",
	"POST Reseller Customer Link",
	"PUT Reseller Customer Link/<link>",
	"DELETE Reseller Customer Link/<link>",
	"GET Employee",
	"GET Leave Application",
	"GET platform_core.api.access.list_role_permissions",
	"POST User",
)


class TestResellerAdminFixture(panel_roles.RoleFixtureContract, unittest.TestCase):
	ROLE = ROLE


class TestResellerAdminHttp(reseller_checks.ResellerChecks, panel_roles.PanelRoleHttpCase):
	ROLE = ROLE
	USER = USER
	FORBIDDEN_ROLES = (
		panel_roles.PLATFORM_OPERATOR,
		panel_roles.TENANT_ADMIN,
		panel_roles.TENANT_ADMIN_ASSISTANT,
		panel_roles.RESELLER_ASSISTANT,
	)

	def test_admin_sends_a_new_customer_request(self):
		before = self.count_requests()

		response = self.call(
			self.login(),
			"POST",
			RESELLER_API + "request_customer",
			customer_name="Yeni Örnek Müşteri",
			contact_email="yeni.musteri@example.test",
		)

		self.assertEqual(response.status_code, 200, response.data[:300])
		name = response.json["message"]["name"]
		self.assertEqual(self.count_requests(), before + 1)
		# The request belongs to the reseller tenant that sent it, whatever the body says.
		self.assertEqual(frappe.db.get_value(REQUEST_DOCTYPE, name, "reseller_tenant"), self.site)

	def test_admin_cannot_send_a_request_for_another_reseller(self):
		response = self.call(
			self.login(),
			"POST",
			RESELLER_API + "request_customer",
			customer_name="Baska Örnek Müşteri",
			contact_email="baska.musteri@example.test",
			reseller_tenant=panel_roles.OTHER_RESELLER,
		)

		self.assertIn(response.status_code, (200, 403, 417), response.data[:300])
		self.assertFalse(frappe.db.exists(REQUEST_DOCTYPE, {"reseller_tenant": panel_roles.OTHER_RESELLER}))
