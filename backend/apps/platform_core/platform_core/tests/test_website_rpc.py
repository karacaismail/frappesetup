from unittest.mock import patch

import frappe
from frappe.auth import get_logged_user
from frappe.desk.form.load import getdoctype
from frappe.tests import IntegrationTestCase
from werkzeug.wrappers import Request

from platform_core.kabuk.metadata import visible_schema
from platform_core.kabuk.metadata_policy import MetadataPolicy
from platform_core.kabuk.native_metadata import (
	guard_native_metadata,
	resolve_method,
	resolve_request_target,
	website_method_allowed,
)


class TestWebsiteRPC(IntegrationTestCase):
	def test_denial_message_has_turkish_translation(self):
		request = Request.from_values(path="/api/method/shell_test_method")
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "form_dict", frappe._dict(), create=True),
			patch.object(frappe.local, "lang", "tr", create=True),
			patch.dict(frappe.session, {"user": "website-user@example.test"}),
			patch("platform_core.kabuk.native_metadata.is_system_user", return_value=False),
			patch("platform_core.kabuk.native_metadata.resolve_request_target", return_value=object()),
		):
			with self.assertRaises(frappe.PermissionError) as denied:
				guard_native_metadata()
		self.assertEqual(str(denied.exception), "Bu yöntemi çağ\u0131rma izniniz yok.")

	def test_invalid_allowlist_entry_does_not_change_valid_entries(self):
		with patch.object(
			frappe,
			"get_hooks",
			return_value=[None, "frappe.auth.missing_test_method", "frappe.auth.get_logged_user"],
		):
			self.assertTrue(website_method_allowed(get_logged_user))
			self.assertFalse(website_method_allowed(getdoctype))

	def test_visible_schema_rejects_a_different_session_user(self):
		meta = frappe.get_meta("ToDo")
		with self.assertRaises(frappe.PermissionError):
			visible_schema(meta, meta.as_dict(), "Guest", MetadataPolicy())

	def test_form_rpc_targets_and_aliases(self):
		method = "frappe.desk.form.load.getdoctype"
		alias = "frappe.tests.test_form_load.getdoctype"
		for path, command in (
			(f"/api/method/{method}", None),
			(f"/api/v1/method/{method}", None),
			(f"/api/v2/method/{method}", None),
			("/", method),
			(f"/api/method/{alias}", None),
			(f"/api/v2/method/{alias}", None),
			("/", alias),
			(f"/api/method/{alias}", method),
		):
			with self.subTest(path=path, command=command):
				self.assertIs(resolve_request_target(Request.from_values(path=path), command), getdoctype)

	def test_desktop_does_not_resolve_or_filter_rpc(self):
		self.assertEqual(frappe.session.user, "Administrator")
		request = Request.from_values(path="/api/method/xyz")
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "form_dict", frappe._dict(), create=True),
			patch("platform_core.kabuk.native_metadata.resolve_request_target") as resolve,
		):
			guard_native_metadata()
		resolve.assert_not_called()

	def test_unresolved_rpc_uses_validation_error(self):
		for path, command in (("/api/method/xyz", None), ("/", "xyz")):
			with self.subTest(path=path), self.assertRaises(frappe.ValidationError):
				resolve_request_target(Request.from_values(path=path), command)

	def test_unresolved_rpc_message_has_turkish_translation(self):
		request = Request.from_values(path="/api/method/xyz")
		with patch.object(frappe.local, "lang", "tr", create=True):
			with self.assertRaises(frappe.ValidationError) as unresolved:
				resolve_request_target(request, None)
		self.assertEqual(str(unresolved.exception), "\u0130stenen yöntem bulunamad\u0131.")

	def test_unexpected_rpc_lookup_failure_is_not_a_validation_error(self):
		for target, doctype in (
			("platform_core.kabuk.native_metadata.load_doctype_module", "ToDo"),
			("frappe.get_attr", None),
		):
			with (
				self.subTest(target=target),
				patch(target, side_effect=RuntimeError("Unexpected lookup failure")),
				self.assertRaisesRegex(RuntimeError, "Unexpected lookup failure"),
			):
				resolve_method("frappe.auth.get_logged_user", doctype=doctype)

	def test_installed_allowlist_compares_callables(self):
		self.assertTrue(website_method_allowed(get_logged_user))
		self.assertFalse(website_method_allowed(getdoctype))

	def test_request_override_is_compared_to_the_allowed_function(self):
		path = "/api/v2/method/platform_core.api.shell.get_bootstrap"
		with patch.object(
			frappe, "override_whitelisted_method", return_value="frappe.desk.form.load.getdoctype"
		):
			target = resolve_request_target(Request.from_values(path=path), None)
		self.assertIs(target, getdoctype)
		self.assertFalse(website_method_allowed(target))
