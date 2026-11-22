from unittest.mock import patch

import frappe
from frappe.auth import get_logged_user
from frappe.desk.form.load import getdoctype
from frappe.tests import IntegrationTestCase
from werkzeug.wrappers import Request

from platform_core.kabuk.native_metadata import (
	guard_native_metadata,
	resolve_request_target,
	website_method_allowed,
)


class TestWebsiteRPC(IntegrationTestCase):
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
