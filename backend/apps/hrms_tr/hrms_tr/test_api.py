"""Check the approval endpoint's transport and record permission boundaries."""

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from hrms_tr import leave
from hrms_tr.api import approve_leave


def raise_permission_error(message, exc=frappe.PermissionError, **kwargs):
	raise exc(message)


class ApprovalEndpointTest(TestCase):
	def test_approve_leave_guest_denied(self):
		with (
			patch.object(frappe, "session", {"user": "Guest"}),
			patch.object(frappe, "response", {}),
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(approve_leave)

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
			fake.throw.side_effect = lambda message: raise_permission_error(message, frappe.ValidationError)
			with self.assertRaises(frappe.ValidationError) as error:
				approve_leave("LEAVE-STALE-0001", "2026-11-22 12:00:00")
		self.assertEqual(error.exception.http_status_code, 417)
		fake.get_doc.assert_called_once_with("Leave Application", "LEAVE-STALE-0001", for_update=True)
		doc.submit.assert_not_called()
		self.assertEqual(doc.status, "Open")
