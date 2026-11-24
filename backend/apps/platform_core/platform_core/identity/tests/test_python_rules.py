"""Regression tests for the Python rule self-audit (docs/standartlar/frappe-python-standartlari.md).

Each test names the rule it proves:
- G-15: after deletion no Version or Comment keeps the raw `sub` or the old e-mail of the identity link,
  and no "Deleted Document" copy of the link is written.
- M-2: the mobile token path refuses a deleted identity, like sign-in does.
- V-8: two first links for the same identity do not end in a server error.
- G-6: state-changing guest wrappers accept POST only.
- G-7: every guest endpoint is rate limited.
- G-8: endpoint parameters and results carry type hints.
- P-3: anonymization reads growing lists page by page; rows after the first page are changed too.
"""

import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.api import auth as auth_api
from platform_core.api import identity as identity_api
from platform_core.identity import anonymization, anonymization_scope, login_policy, provider_setup, sign_in
from platform_core.identity.tests import helpers as h

SUBJECT = "sub-kural-ornek-31"
EMAIL = "kural.ornek.31@example.test"
LINK = "PLT Identity Link"


class TestPythonRules(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def setUp(self):
		super().setUp()
		self._cleanup()
		self.addCleanup(self._cleanup)
		h.ensure_user(EMAIL)
		h.reset_rate_limits()
		self.addCleanup(h.reset_rate_limits)
		frappe.db.commit()

	@staticmethod
	def _clear_deletion(subject: str):
		filters = {"name": anonymization.identity_hash(h.ISSUER, subject)}
		record = frappe.db.get_value("Platform Identity Deletion", filters, ["user", "state"], as_dict=True)
		if record and record.state == anonymization.ANONYMIZED:
			frappe.delete_doc("User", record.user, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.delete("Platform Identity Deletion", filters)

	@classmethod
	def _cleanup(cls):
		h.clear_sessions_of(EMAIL)
		frappe.db.delete(LINK, {"subject": SUBJECT})
		cls._clear_deletion(SUBJECT)
		for name in frappe.get_all("Contact Email", filters={"email_id": EMAIL}, pluck="parent"):
			frappe.delete_doc("Contact", name, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.delete("Activity Log", {"owner": EMAIL})
		frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.commit()

	def service(self, name, body):
		signed = self.key.sign(h.access_payload())
		return h.request(
			h.new_client().post,
			f"/api/method/platform_core.api.identity.{name}",
			json=body,
			headers={"Authorization": f"Bearer {signed}"},
		)

	# --- G-15 ---------------------------------------------------------------------------------------

	def test_no_history_of_the_link_keeps_the_raw_identity(self):
		subject = f"reconciliation-history-{frappe.generate_hash(length=12)}"
		link = h.make_link(subject, EMAIL)
		self.addCleanup(self._clear_deletion, subject)
		# The link tracks changes. A desk edit leaves a Version row with the raw values.
		frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": LINK,
				"docname": link.name,
				"data": json.dumps({"changed": [["subject", "sub-eski", subject], ["user", "x", EMAIL]]}),
			}
		).insert(ignore_permissions=True)
		unrelated = frappe.get_doc("User", "Administrator").add_comment("Comment", EMAIL)
		self.addCleanup(frappe.db.delete, "Comment", {"name": unrelated.name})
		frappe.db.commit()
		self.assertTrue(frappe.db.exists("Version", {"ref_doctype": LINK, "docname": link.name}))
		response = self.service("anonymize_user", {"issuer": h.ISSUER, "subject": subject})
		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		self.assertFalse(frappe.db.exists("Version", {"ref_doctype": LINK, "docname": link.name}))
		self.assertFalse(
			frappe.db.exists("Deleted Document", {"deleted_doctype": LINK, "deleted_name": link.name})
		)
		for doctype, field in (("Version", "data"), ("Comment", "content"), ("Deleted Document", "data")):
			for value in frappe.get_all(doctype, filters={field: ("like", f"%{subject}%")}, pluck=field):
				self.fail(f"{doctype} keeps the raw sub: {value[:120]}")
		self.assertEqual(frappe.db.get_value("Comment", unrelated.name, "content"), EMAIL)
		for value in frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "User",
				"reference_name": response.json["message"]["user"],
				"content": ("like", f"%{EMAIL}%"),
			},
			pluck="content",
		):
			self.fail(f"Comment keeps the old e-mail: {value[:120]}")

	# --- M-2 ----------------------------------------------------------------------------------------

	def test_mobile_token_of_a_deleted_identity_is_refused(self):
		h.make_link(SUBJECT, EMAIL)
		anonymization.disable_step(h.ISSUER, SUBJECT)
		frappe.db.set_value("User", EMAIL, "enabled", 1)
		frappe.db.commit()
		token = self.key.sign(
			h.access_payload(
				sub=SUBJECT,
				azp="mobile",
				scope="openid mobile",
				sid="12121212-1212-4121-8121-121212121212",
				auth_time=int(time.time()) - 30,
			)
		)
		from platform_core.identity import api as identity_api
		from platform_core.identity.exceptions import ServiceTokenRejected

		with self.assertRaises(ServiceTokenRejected):
			identity_api.verify_mobile_token(token)

	# --- V-8 ----------------------------------------------------------------------------------------

	def test_stale_transaction_refuses_the_race_and_a_fresh_request_reuses_the_link(self):
		site = frappe.local.site
		filters = {"issuer": h.ISSUER, "subject": SUBJECT}
		self.assertIsNone(frappe.db.get_value(LINK, filters, "name"))

		def first_request():
			frappe.init(site=site)
			frappe.connect()
			try:
				frappe.set_user("Administrator")
				name = sign_in.create_link(h.ISSUER, SUBJECT, EMAIL)
				frappe.db.commit()
				return name
			finally:
				frappe.destroy()

		with ThreadPoolExecutor(max_workers=1) as executor:
			first = executor.submit(first_request).result(timeout=15)
		# This connection opened its snapshot before the winner committed.
		with self.assertRaises(sign_in.SignInRefusedError) as refused:
			sign_in.create_link(h.ISSUER, SUBJECT, EMAIL)
		self.assertEqual(refused.exception.status, 403)
		frappe.db.rollback()
		second = sign_in.create_link(h.ISSUER, SUBJECT, EMAIL)
		self.assertEqual(first, second)
		self.assertEqual(frappe.db.count(LINK, {"subject": SUBJECT}), 1)

	def test_first_link_racing_with_another_user_is_refused(self):
		h.ensure_user(h.AYSE)
		sign_in.create_link(h.ISSUER, SUBJECT, h.AYSE)
		frappe.db.commit()
		with self.assertRaises(sign_in.SignInRefusedError) as refused:
			sign_in.create_link(h.ISSUER, SUBJECT, EMAIL)
		self.assertEqual(refused.exception.status, 403)

	# --- G-6 ----------------------------------------------------------------------------------------

	def test_state_changing_guest_wrappers_accept_post_only(self):
		for name in ("reset_password", "update_password", "sign_up", "send_login_link", "ldap_login"):
			function = getattr(login_policy, name)
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(function), ["POST"], name)
		response = h.request(
			h.new_client().get,
			"/api/method/frappe.core.doctype.user.user.sign_up",
			query_string={"email": "x@example.test", "full_name": "X", "redirect_to": "/"},
		)
		self.assertEqual(response.status_code, 403, response.data[:200])

	# --- G-7 ----------------------------------------------------------------------------------------

	def test_every_guest_endpoint_is_rate_limited(self):
		paths = [
			("post", "/api/method/platform_core.api.auth.get_login_url"),
			("get", "/api/method/platform_core.api.auth.start_login"),
			("get", "/api/method/platform_core.api.auth.keycloak_callback"),
			("post", "/api/method/platform_core.api.keycloak_backchannel_logout"),
			("post", "/api/method/platform_core.api.atonota_login.verification_notice"),
		]
		for original, (_name, methods) in login_policy.GATED_FUNCTIONS.items():
			paths.append(("post" if "POST" in methods else "get", f"/api/method/{original}"))
		limits = {
			"/api/method/platform_core.api.keycloak_backchannel_logout": 300,
			"/api/method/platform_core.api.atonota_login.verification_notice": 300,
		}
		with h.SiteSettings({"identity_keycloak_only": 1}):
			for verb, path in paths:
				h.reset_rate_limits()
				limit = limits.get(path, login_policy.GUEST_LIMIT)
				statuses = set()
				for _number in range(limit + 1):
					statuses.add(h.request(getattr(h.new_client(), verb), path).status_code)
					if 429 in statuses:
						break
				self.assertIn(429, statuses, path)

	# --- G-8 ----------------------------------------------------------------------------------------

	def test_endpoints_carry_type_hints(self):
		functions = [
			identity_api.provision,
			identity_api.set_enabled,
			identity_api.change_email,
			identity_api.anonymize_user,
			auth_api.logout,
			auth_api.setup_keycloak_login,
		]
		functions += [getattr(login_policy, name) for name, _methods in login_policy.GATED_FUNCTIONS.values()]
		for function in functions:
			target = inspect.unwrap(function)
			signature = inspect.signature(target)
			self.assertIsNot(signature.return_annotation, inspect.Signature.empty, target.__name__)
			for parameter in signature.parameters.values():
				self.assertIsNot(
					parameter.annotation, inspect.Parameter.empty, f"{target.__name__}.{parameter.name}"
				)

	# --- P-3 ----------------------------------------------------------------------------------------

	def test_contact_without_email_requires_an_exact_user_link(self):
		contact = frappe.get_doc({"doctype": "Contact", "first_name": "Case variant fixture"})
		contact.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Contact", contact.name, ignore_permissions=True)
		frappe.db.set_value("Contact", contact.name, "user", EMAIL.upper())

		owned = anonymization_scope._ownership(EMAIL)
		self.assertIn(contact.name, owned.shared_contacts)
		self.assertNotIn(contact.name, owned.contacts)

	def test_contact_ownership_reads_email_rows_in_batches(self):
		names = set()
		for label in ("First", "Second", "Third"):
			doc = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": f"{label} audit fixture",
					"email_ids": [{"email_id": EMAIL, "is_primary": 1}],
				}
			).insert(ignore_permissions=True)
			names.add(doc.name)
		with patch.object(frappe, "get_all", wraps=frappe.get_all) as read:
			owned = anonymization_scope._ownership(EMAIL)
		self.assertLessEqual(names, owned.contacts)
		address_reads = [
			call
			for call in read.call_args_list
			if call.args == ("Contact Email",) and "parent" in call.kwargs["filters"]
		]
		self.assertEqual(len(address_reads), 1)

	def test_shared_contact_reads_are_batched_and_secondary_email_stays(self):
		names = set()
		other_email = "remaining.contact@example.test"
		for label in ("First", "Second", "Third"):
			contact = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": f"{label} shared fixture",
					"email_ids": [{"email_id": EMAIL, "is_primary": 1}, {"email_id": other_email}],
				}
			).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "Contact", contact.name, force=True, ignore_permissions=True)
			names.add(contact.name)
		owned = frappe._dict(contacts=set(), shared_contacts=names, addresses=set(), shared_addresses=set())
		with patch.object(frappe, "get_all", wraps=frappe.get_all) as read:
			anonymization_scope._extra_records(EMAIL, "replacement@example.test", "", owned)
		self.assertEqual(
			frappe.get_all("Contact Email", filters={"parent": ("in", list(names))}, pluck="email_id"),
			[other_email] * len(names),
		)
		for name in names:
			self.assertEqual(frappe.db.get_value("Contact", name, "email_id"), other_email)
		email_reads = [call for call in read.call_args_list if call.args == ("Contact Email",)]
		self.assertEqual(len(email_reads), 1)

	def test_bound_text_rows_are_read_as_needed(self):
		with (
			patch.object(anonymization_scope, "PAGE_SIZE", 1),
			patch.object(
				frappe,
				"get_all",
				side_effect=[[{"name": "a", "content": "first"}], [{"name": "b", "content": "second"}], []],
			) as read_page,
		):
			rows = iter(anonymization_scope._bound_rows("Comment", "owner", EMAIL, ["content"]))
			self.assertEqual(next(rows)["name"], "a")
			self.assertEqual(read_page.call_count, 1)
			self.assertEqual(next(rows)["name"], "b")
			self.assertEqual(read_page.call_count, 2)
			self.assertEqual(list(rows), [])

	def test_rows_after_the_first_page_are_anonymized(self):
		h.make_link(SUBJECT, EMAIL)
		names = []
		for number in range(5):
			doc = frappe.get_doc(
				{
					"doctype": "Activity Log",
					"subject": f"Ornek {EMAIL} {number}",
					"user": EMAIL,
					"full_name": "Kural Ornek",
				}
			).insert(ignore_permissions=True)
			names.append(doc.name)
		frappe.db.commit()
		with patch.object(anonymization_scope, "PAGE_SIZE", 2):
			response = self.service("anonymize_user", {"issuer": h.ISSUER, "subject": SUBJECT})
		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		for name in names:
			row = frappe.db.get_value("Activity Log", name, ["subject", "full_name"], as_dict=True)
			self.assertNotIn(EMAIL, row.subject or "")
			self.assertNotEqual(row.full_name, "Kural Ornek")
