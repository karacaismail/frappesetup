"""The corporate provider exception record is immutable (G-160, AJA-229, design section 4).

A record is never changed after approval and never deleted. A change opens a new record that
supersedes the old one. A revocation record ends the exception. The sync step exports only the
current grants; the `apply` command reads that file.
"""

import json
import os
import tempfile
from datetime import timedelta
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from platform_core.identity import enterprise_membership, enterprise_rules, enterprise_sync
from platform_core.identity.tests import helpers as h

DOCTYPE = "PLT Enterprise IdP Exception"
OWNER = "kurulus.sahibi@example.test"
SECURITY = "guvenlik.sorumlusu@example.test"
ISSUER = "https://login.microsoftonline.com/0b5e3b55-1f4c-4d2e-9a77-1c2d3e4f5a6b/v2.0"
ALIAS = "test-acme-entra"


class TestEnterpriseException(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.ensure_user(OWNER, "System User", ["System Manager"])
		h.ensure_user(SECURITY, "System User", ["System Manager"])

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.delete(DOCTYPE, {"provider_alias": ("like", "test-%")})
		self.addCleanup(frappe.set_user, "Administrator")

	def request(self, alias=ALIAS, organization="acme", supersedes=None, **changes):
		frappe.set_user(OWNER)
		now = now_datetime()
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"kind": "grant",
				"provider_alias": alias,
				"issuer": ISSUER,
				"organization": organization,
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
				# The test picks a date. The code has no default length (a product decision).
				"expires_on": now + timedelta(days=30),
				"supersedes": supersedes,
				**changes,
			}
		).insert()
		frappe.set_user("Administrator")
		return doc

	def approve(self, doc, approver=SECURITY, principal="human_session"):
		frappe.set_user(approver)
		try:
			return enterprise_membership.approve(doc.name, principal=principal)
		finally:
			frappe.set_user("Administrator")

	def test_requester_is_the_session_user(self):
		doc = self.request(requested_by=SECURITY)
		self.assertEqual(doc.requested_by, OWNER)

	def test_approval_fields_cannot_be_set_on_insert(self):
		with self.assertRaises(frappe.ValidationError):
			self.request(approved_by=SECURITY)

	def test_expiry_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			self.request(expires_on=None)

	def test_request_rules_run_on_insert(self):
		with self.assertRaises(frappe.ValidationError):
			self.request(issuer="https://login.microsoftonline.com/common/v2.0")
		with self.assertRaises(frappe.ValidationError):
			self.request(alias="google")

	def test_approval_fills_the_fields(self):
		doc = self.approve(self.request())
		self.assertEqual(doc.approved_by, SECURITY)
		self.assertEqual(doc.approval_principal, "human_session")
		self.assertTrue(doc.approved_on)

	def test_self_and_agent_approval_are_refused(self):
		doc = self.request()
		with self.assertRaises(frappe.ValidationError):
			self.approve(doc, approver=OWNER)
		with self.assertRaises(frappe.ValidationError):
			self.approve(doc, principal="agent_token")
		self.assertFalse(frappe.db.get_value(DOCTYPE, doc.name, "approved_by"))

	def test_unapproved_record_takes_only_approval_fields(self):
		doc = self.request()
		doc.reason = "Changed reason."
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_approved_record_cannot_change(self):
		doc = self.approve(self.request())
		doc.reload()
		doc.expires_on = now_datetime() + timedelta(days=60)
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		doc.reload()
		doc.allowed_domains[0].domain = "other.example"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_record_cannot_be_deleted(self):
		doc = self.request()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc(DOCTYPE, doc.name, ignore_permissions=True, force=True)
		self.assertTrue(frappe.db.exists(DOCTYPE, doc.name))

	def test_no_role_may_write_or_delete(self):
		for permission in frappe.get_meta(DOCTYPE).permissions:
			self.assertFalse(permission.write, permission.role)
			self.assertFalse(permission.delete, permission.role)

	def test_change_opens_new_record(self):
		first = self.approve(self.request())
		with self.assertRaises(frappe.ValidationError):
			# A second record for the same pair must supersede the current one.
			self.request()
		second = self.approve(self.request(supersedes=first.name))
		self.assertTrue(frappe.db.exists(DOCTYPE, first.name))
		self.assertEqual(enterprise_membership.current_exception(ALIAS, "acme").name, second.name)

	def test_unapproved_change_keeps_the_old_record_current(self):
		first = self.approve(self.request())
		self.request(supersedes=first.name)
		self.assertEqual(enterprise_membership.current_exception(ALIAS, "acme").name, first.name)

	def test_revocation_ends_exception(self):
		first = self.approve(self.request())
		frappe.set_user(SECURITY)
		revocation = enterprise_membership.revoke(first.name, "The organisation left.")
		frappe.set_user("Administrator")
		self.assertEqual(revocation.kind, "revocation")
		self.assertEqual(revocation.supersedes, first.name)
		self.assertIsNone(enterprise_membership.current_exception(ALIAS, "acme"))
		self.assertTrue(frappe.db.exists(DOCTYPE, first.name))

	def test_one_provider_for_one_organisation(self):
		self.approve(self.request())
		with self.assertRaises(frappe.ValidationError):
			self.request(organization="other")

	def test_sync_exports_only_current_grants(self):
		kept = self.approve(self.request())
		ended = self.approve(self.request(alias="test-ended"))
		frappe.set_user(SECURITY)
		enterprise_membership.revoke(ended.name, "Closed.")
		frappe.set_user("Administrator")
		self.request(alias="test-waiting")
		folder = tempfile.TemporaryDirectory()
		self.addCleanup(folder.cleanup)
		path = os.path.join(folder.name, "exceptions.json")
		enterprise_sync.export_exceptions(path)
		records = [
			r for r in json.load(open(path, encoding="utf-8")) if r["provider_alias"].startswith("test-")
		]
		self.assertEqual([r["name"] for r in records], [kept.name])
		checked = enterprise_rules.check_record(records[0])
		self.assertEqual(checked["allowed_domains"], ["acme.example"])
		self.assertEqual(os.stat(path).st_mode & 0o077, 0)


class TestApprovalPrincipal(IntegrationTestCase):
	"""Only a cookie session with a checked CSRF token approves. An agent token never does."""

	def principal(self, headers, token="csrf-1"):
		with (
			mock.patch.object(
				frappe, "get_request_header", side_effect=lambda key, default=None: headers.get(key)
			),
			mock.patch.dict(frappe.session.data, {"csrf_token": token}),
		):
			return enterprise_membership.request_principal()

	def test_cookie_session_with_csrf_is_human(self):
		frappe.set_user(SECURITY)
		self.addCleanup(frappe.set_user, "Administrator")
		self.assertEqual(self.principal({"X-Frappe-CSRF-Token": "csrf-1"}), "human_session")

	def test_bearer_token_or_missing_csrf_is_not_human(self):
		frappe.set_user(SECURITY)
		self.addCleanup(frappe.set_user, "Administrator")
		bearer = {"Authorization": "Bearer x", "X-Frappe-CSRF-Token": "csrf-1"}
		self.assertEqual(self.principal(bearer), "other")
		self.assertEqual(self.principal({}), "other")
		self.assertEqual(self.principal({"X-Frappe-CSRF-Token": "wrong"}), "other")
		self.assertEqual(self.principal({"X-Frappe-CSRF-Token": "csrf-1"}, token=None), "other")
