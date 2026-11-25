"""Panel role “Reseller Assistant” (G-170, AJA-831). Written before the code (D-2).

The reseller admin gives this role to a person of the own company. The person only reads the
customer list and the site state. Every write request is refused. Every ban of the reseller admin
holds for this role too.

The lists below say what the panel shows. The panel test
`tests/e2e/rol-reseller-assistant.spec.ts` checks them.
Example: the role opens “Müşteriler” and does not see the new customer button.
"""

# The panel texts are Turkish. Their dotless i letters are intended.
# ruff: noqa: RUF001

import unittest

from platform_core.access.tests import panel_roles, reseller_checks
from platform_core.access.tests.panel_roles import RESELLER_API

ROLE = panel_roles.RESELLER_ASSISTANT
USER = "pr.bayi.yardimci@example.test"

# Menu groups the role sees (G-170). “Müşteriler” and “Site ve plan” are read only.
MENU = ("Hesap", "Müşteriler", "Site ve plan")
MENU_HIDDEN = ("Yönetim", "İzin talepleri", "Yapay zekâ işlemleri", "Yapay zekâ sağlayıcıları")
# Pages the role opens and pages it cannot open.
PAGES_OPEN = ("/account", "/site-plan", "/customers")
PAGES_CLOSED = ("/administration", "/administration/ai-providers", "/hr", "/ai-operations")
# Action buttons. The role sees none of them.
BUTTONS_SHOWN = ()
BUTTONS_HIDDEN = ("Yeni müşteri isteği", "Planı değiştir", "Erişimi açıkla")
# API requests the role is refused (HTTP 403, business data 403 or 404).
DENIED = (
	"POST platform_core.api.reseller.request_customer",
	"POST platform_core.api.reseller.approve_customer_request",
	"GET platform_core.api.reseller.customer_status (customer of another reseller)",
	"GET platform_core.api.reseller.customer_status (unknown customer)",
	"POST Reseller Customer Link",
	"PUT Reseller Customer Link/<link>",
	"DELETE Reseller Customer Link/<link>",
	"GET Employee",
	"GET Leave Application",
	"GET platform_core.api.access.list_role_permissions",
	"POST User",
)


class TestResellerAssistantFixture(panel_roles.RoleFixtureContract, unittest.TestCase):
	ROLE = ROLE


class TestResellerAssistantHttp(reseller_checks.ResellerChecks, panel_roles.PanelRoleHttpCase):
	ROLE = ROLE
	USER = USER
	FORBIDDEN_ROLES = (
		panel_roles.PLATFORM_OPERATOR,
		panel_roles.RESELLER_ADMIN,
		panel_roles.TENANT_ADMIN,
		panel_roles.TENANT_ADMIN_ASSISTANT,
	)

	def test_assistant_cannot_send_a_new_customer_request(self):
		before = self.count_requests()

		self.assert_denied(
			self.login(),
			"POST",
			RESELLER_API + "request_customer",
			customer_name="Yeni Örnek Müşteri",
			contact_email="yeni.musteri@example.test",
		)

		self.assertEqual(self.count_requests(), before)
