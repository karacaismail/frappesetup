"""Check that legacy routes and report execution cannot disclose leave data."""

from unittest import TestCase
from unittest.mock import patch

import frappe

from hrms_tr import hrms_endpoints
from hrms_tr.test_api import raise_permission_error


class DeniedLegacyEndpointTest(TestCase):
	def test_deny_legacy_leave_query_guest_denied(self):
		with (
			patch.object(frappe, "session", {"user": "Guest"}),
			patch.object(frappe, "response", {}),
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(hrms_endpoints.deny_legacy_leave_query)

	def test_deny_legacy_leave_query_foreign_data_denied(self):
		with (
			patch.object(frappe, "session", {"user": "employee@example.test"}),
			patch.object(hrms_endpoints, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				hrms_endpoints.deny_legacy_leave_query()

	def test_attendance_warning_override_is_not_whitelisted(self):
		with (
			patch.object(frappe, "session", {"user": "employee@example.test"}),
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(hrms_endpoints.AttendanceRequestAccess.get_attendance_warnings)
