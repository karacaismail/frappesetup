"""HRMS TR's app declaration exposes the approval only as a write tool."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from hrms_tr import ai_tools


class ApprovalToolTest(unittest.TestCase):
	def test_registration_and_tools_are_documented(self):
		self.assertTrue((ai_tools.declarations.__doc__ or "").strip())
		for tool in ai_tools.declarations():
			with self.subTest(tool=tool["name"]):
				self.assertTrue(tool["description"].strip())

	def test_has_preview_and_separate_handler(self):
		(tool,) = ai_tools.declarations()
		self.assertEqual(tool["name"], "approve_leave")
		self.assertEqual(tool["kind"], "write")
		self.assertIs(tool["versioned"], True)
		self.assertEqual(tool["roles"], ["HRMS TR Manager", "HRMS TR Admin"])
		self.assertNotEqual(tool["preview"], tool["handler"])

	def test_confirmation_cannot_be_passed_as_an_argument(self):
		with self.assertRaises(ValidationError):
			ai_tools.ApprovalArguments(name="HR-LAP-0001", confirm=True)

	def test_preview_uses_shared_change_keys_without_personal_details(self):
		doc = SimpleNamespace(
			doctype="Leave Application",
			name="HR-LAP-0001",
			modified="2026-11-22 12:00:00",
			status="Open",
			docstatus=0,
			employee_name="Synthetic Employee",
			from_date="2026-12-01",
			to_date="2026-12-03",
			total_leave_days=3,
		)
		with (
			patch.object(ai_tools.leave, "pending_leave", return_value=doc),
			patch.object(ai_tools, "_", side_effect=lambda message: message),
		):
			preview = ai_tools.preview_approval(doc.name)
		self.assertEqual(preview["target_version"], doc.modified)
		self.assertEqual(preview["details"], {"name": doc.name})
		self.assertTrue(preview["changes"])
		for change in preview["changes"]:
			self.assertEqual(set(change), {"fieldname", "label", "old", "new"})
		encoded = json.dumps(preview)
		for private_value in (doc.employee_name, doc.from_date, doc.to_date):
			self.assertNotIn(private_value, encoded)
		self.assertNotIn("total_leave_days", encoded)

	def test_ai_arguments_do_not_accept_a_client_version(self):
		self.assertEqual(ai_tools.ApprovalArguments(name="HR-LAP-0001").name, "HR-LAP-0001")
		with self.assertRaises(ValidationError):
			ai_tools.ApprovalArguments(name="HR-LAP-0001", version="2026-11-22 12:00:00")

	def test_ai_handler_does_not_persist_hrms_validation_details(self):
		import frappe

		with (
			patch.object(
				ai_tools.leave, "approve", side_effect=frappe.ValidationError("Private employee conflict")
			),
			patch.object(ai_tools, "frappe") as framework,
			patch.object(ai_tools, "_", side_effect=lambda value: value),
		):
			framework.ValidationError = frappe.ValidationError
			framework.PermissionError = frappe.PermissionError
			with self.assertRaisesRegex(frappe.ValidationError, "could not be approved") as raised:
				ai_tools.execute_approval("HR-LAP-0001")
			framework.clear_messages.assert_called_once_with()
		self.assertNotIn("Private employee conflict", str(raised.exception))
