"""Check the approval endpoint's transport and record permission boundaries."""

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from hrms_tr import leave
from hrms_tr.api import approve_leave, cancel_leave, get_leave_approver


def raise_permission_error(message, exc=frappe.PermissionError, **kwargs):
	raise exc(message)


class ApprovalEndpointTest(TestCase):
	def test_approve_leave_guest_denied(self):
		self.assert_guest_denied(approve_leave)

	def test_cancel_leave_guest_denied(self):
		self.assert_guest_denied(cancel_leave)

	def test_get_leave_approver_guest_denied(self):
		self.assert_guest_denied(get_leave_approver)

	def assert_guest_denied(self, endpoint):
		with (
			patch.object(frappe, "session", {"user": "Guest"}),
			patch.object(frappe, "response", {}),
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(endpoint)

	def test_cancel_leave_foreign_data_denied(self):
		doc = Mock()
		doc.check_permission.side_effect = frappe.PermissionError("Foreign application")
		with patch.object(leave, "frappe") as fake:
			fake.get_roles.return_value = ["HRMS TR Admin"]
			fake.get_doc.return_value = doc
			with self.assertRaises(frappe.PermissionError):
				cancel_leave("LEAVE-FOREIGN-0001", "2026-11-22 12:00:00")
		fake.get_doc.assert_called_once_with("Leave Application", "LEAVE-FOREIGN-0001", for_update=True)
		doc.check_permission.assert_called_once_with("read")
		doc.cancel.assert_not_called()

	def test_get_leave_approver_foreign_data_denied(self):
		native_module, method_name = leave.HRMS_APPROVER_METHOD.rsplit(".", 1)
		native_lookup = getattr(frappe.get_module(native_module), method_name)
		with (
			patch.object(leave, "frappe") as fake,
			patch(f"{native_module}.validate_leave_access", side_effect=frappe.PermissionError) as validate,
			patch(f"{native_module}.get_employee_leave_approver") as lookup,
		):
			fake.db.exists.return_value = True
			fake.get_attr.return_value = native_lookup
			with self.assertRaises(frappe.PermissionError):
				get_leave_approver("EMP-FOREIGN-0001")
		fake.get_attr.assert_called_once_with(leave.HRMS_APPROVER_METHOD)
		validate.assert_called_once_with("EMP-FOREIGN-0001", None)
		lookup.assert_not_called()

	def test_approve_leave_foreign_data_denied(self):
		doc = Mock()
		doc.check_permission.side_effect = frappe.PermissionError("Foreign application")
		with patch.object(leave, "frappe") as fake:
			fake.get_roles.return_value = ["HRMS TR Manager"]
			fake.get_doc.return_value = doc
			with self.assertRaises(frappe.PermissionError):
				approve_leave("LEAVE-FOREIGN-0001", "2026-11-22 12:00:00")
		doc.check_permission.assert_called_once_with("read")
		doc.submit.assert_not_called()

	def test_approve_leave_stale_version_is_rejected_under_lock(self):
		doc = Mock(employee="EMP-0001", docstatus=0, status="Open", modified="2026-11-22 12:00:01")
		with (
			patch.object(leave, "frappe") as fake,
			patch.object(leave, "_", side_effect=lambda message: message),
		):
			fake.get_roles.return_value = ["HRMS TR Manager"]
			fake.session.user = "manager@example.test"
			fake.db.get_value.return_value = "employee@example.test"
			fake.get_doc.return_value = doc
			fake.TimestampMismatchError = frappe.TimestampMismatchError
			fake.throw.side_effect = raise_permission_error
			with self.assertRaises(frappe.TimestampMismatchError) as error:
				approve_leave("LEAVE-STALE-0001", "2026-11-22 12:00:00")
		self.assertEqual(error.exception.http_status_code, 417)
		fake.get_doc.assert_called_once_with("Leave Application", "LEAVE-STALE-0001", for_update=True)
		doc.submit.assert_not_called()
		self.assertEqual(doc.status, "Open")

	def test_approve_leave_throttles_by_authenticated_user(self):
		from types import SimpleNamespace

		cache = Mock()
		cache.make_key.return_value = b"site:counter"
		cache.get.return_value = 60
		cache.incrby.return_value = 61
		with (
			patch.object(frappe, "request", SimpleNamespace(method="POST")),
			patch.object(frappe, "session", frappe._dict(user="manager@example.test")),
			patch.object(frappe, "cache", cache),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
			patch("frappe.rate_limiter._", side_effect=lambda text: text),
			patch.object(leave, "approve") as approve,
		):
			with self.assertRaises(frappe.RateLimitExceededError):
				approve_leave("HR-LAP-TEST", "2026-11-22 12:00:00")
		cache.make_key.assert_called_once_with("rl:hrms_tr.api.approve_leave:manager@example.test")
		approve.assert_not_called()

	def test_missing_version_raises_native_validation_error(self):
		from hrms_tr import api

		with (
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(api, "_", create=True, side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
			patch.object(leave, "approve") as approve,
		):
			with self.assertRaises(frappe.ValidationError):
				approve_leave("LEAVE-MISSING")
		approve.assert_not_called()
