"""HTTP access checks for the exception approval endpoints (G-160, AJA-229).

A guest never reaches the endpoints. A signed-in user without the approver role cannot approve or
revoke another organisation's record. The record stays unchanged.
"""

from datetime import timedelta

import frappe
from frappe.tests.test_api import FrappeAPITestCase
from frappe.utils import now_datetime

from platform_core.identity.tests import helpers as h

DOCTYPE = "PLT Enterprise IdP Exception"
OWNER = "kurulus.sahibi@example.test"
ISSUER = "https://login.microsoftonline.com/0b5e3b55-1f4c-4d2e-9a77-1c2d3e4f5a6b/v2.0"
ALIAS = "test-http-entra"


class TestExceptionEndpointAccess(FrappeAPITestCase):
	def setUp(self):
		super().setUp()
		h.clear_links()
		h.ensure_user(h.AYSE)
		h.ensure_user(OWNER, "System User", ["System Manager"])
		frappe.set_user("Administrator")
		frappe.db.delete(DOCTYPE, {"provider_alias": ALIAS})
		self.addCleanup(self.remove_records)
		self.record = self.request()
		h.refresh()

	def remove_records(self):
		frappe.set_user("Administrator")
		frappe.db.delete(DOCTYPE, {"provider_alias": ALIAS})
		h.refresh()

	def request(self):
		frappe.set_user(OWNER)
		now = now_datetime()
		try:
			return frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"kind": "grant",
					"provider_alias": ALIAS,
					"issuer": ISSUER,
					"organization": "acme",
					"allowed_domains": [
						{
							"domain": "acme.example",
							"verification_method": "dns-txt",
							"verified_on": now - timedelta(days=1),
							"verification_record": "_atonota-verify.acme.example",
						}
					],
					"reason": "The provider does not send the email_verified claim.",
					"provider_document": "https://docs.example/provider/claims",
					"expires_on": now + timedelta(days=30),
				}
			).insert()
		finally:
			frappe.set_user("Administrator")

	def assert_denied(self, method, payload, *, signed_in):
		with h.SiteSettings(), h.jwks_patch():
			client = h.new_client()
			if signed_in:
				h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
				self.assertEqual(h.logged_user(client), h.AYSE)
			response = h.request(
				client.post,
				f"/api/method/platform_core.identity.enterprise_membership.{method}",
				headers=h.csrf_headers(client),
				data=payload,
			)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json.get("exc_type"), "PermissionError")
		h.refresh()
		self.assertFalse(frappe.db.get_value(DOCTYPE, self.record.name, "approved_by"))
		self.assertFalse(frappe.db.exists(DOCTYPE, {"supersedes": self.record.name}))

	def test_approve_exception_guest_denied(self):
		self.assert_denied("approve_exception", {"name": self.record.name}, signed_in=False)

	def test_approve_exception_foreign_data_denied(self):
		self.assert_denied("approve_exception", {"name": self.record.name}, signed_in=True)

	def test_revoke_exception_guest_denied(self):
		payload = {"name": self.record.name, "reason": "Closed."}
		self.assert_denied("revoke_exception", payload, signed_in=False)

	def test_revoke_exception_foreign_data_denied(self):
		payload = {"name": self.record.name, "reason": "Closed."}
		self.assert_denied("revoke_exception", payload, signed_in=True)
