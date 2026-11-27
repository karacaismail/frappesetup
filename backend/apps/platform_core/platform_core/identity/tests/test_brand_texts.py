"""The product name in messages and emails comes from the `identity_brand_name` setting (AJA-1061).

backend/brand.env is the one source of the name. The deploy step writes it into the
`identity_brand_name` site setting (AJA-1059 plan, section 2). These tests change the setting
and check that the visible text changes with it. The brand values here are test values only.

Frappe emails take the brand from `app_name` (frappe/email/email_body.py, `get_brand_name`).
`turkey_setup.apply` writes `identity_brand_name` into System Settings `app_name`.
"""

from unittest.mock import patch

import frappe
from frappe.email.email_body import get_brand_name
from frappe.tests import IntegrationTestCase

from platform_core.config import turkey_setup
from platform_core.identity import login_accounts
from platform_core.identity.exceptions import IdentityLinkMissing
from platform_core.identity.tests import helpers as h

BRANDS = ("Deneme Marka", "Ikinci Marka")
EMAIL_USER = "marka.ornek@example.test"


class TestBrandTexts(IntegrationTestCase):
	def test_unlinked_session_message_names_the_setting_brand(self):
		for brand in BRANDS:
			with (
				self.subTest(brand=brand),
				h.SiteSettings({"identity_brand_name": brand}),
				patch.dict(frappe.session, {"data": frappe._dict()}),
			):
				with self.assertRaises(IdentityLinkMissing) as caught:
					login_accounts.session_subject()
				self.assertIn(brand, str(caught.exception))

	def test_welcome_email_names_the_setting_brand(self):
		old_system = frappe.db.get_single_value("System Settings", "app_name")
		old_website = frappe.db.get_single_value("Website Settings", "app_name")
		# Website Settings wins over System Settings in get_brand_name, so it stays empty here.
		frappe.db.set_single_value("Website Settings", "app_name", "")
		try:
			user = frappe.get_doc("User", h.ensure_user(EMAIL_USER, user_type="System User"))
			for brand in BRANDS:
				with self.subTest(brand=brand), h.SiteSettings({"identity_brand_name": brand}):
					turkey_setup.apply()
					self.assertEqual(get_brand_name(), brand)
					frappe.db.delete("Email Queue Recipient", {"recipient": EMAIL_USER})
					user.send_welcome_mail_to_user()
					message = frappe.db.get_value(
						"Email Queue",
						{"name": ("in", _queue_names(EMAIL_USER))},
						"message",
						order_by="creation desc",
					)
					self.assertIn(brand, message or "")
		finally:
			frappe.db.set_single_value("System Settings", "app_name", old_system)
			frappe.db.set_single_value("Website Settings", "app_name", old_website)
			frappe.db.rollback()


def _queue_names(recipient: str) -> list[str]:
	return frappe.get_all("Email Queue Recipient", filters={"recipient": recipient}, pluck="parent") or [""]
