"""HRMS TR's app declaration exposes the approval only as a write tool."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from hrms_tr import ai_tools


class ApprovalToolTest(unittest.TestCase):
	def test_has_preview_and_separate_handler(self):
		(tool,) = ai_tools.declarations()
		self.assertEqual(tool["name"], "approve_leave")
		self.assertEqual(tool["kind"], "write")
		self.assertEqual(tool["roles"], ["HRMS TR Manager", "HRMS TR Admin"])
		self.assertNotEqual(tool["preview"], tool["handler"])

	def test_confirmation_cannot_be_passed_as_an_argument(self):
		with self.assertRaises(ValidationError):
			ai_tools.ApprovalArguments(name="HR-LAP-0001", version="test", confirm=True)

	def test_preview_uses_shared_change_keys_without_personal_details(self):
		doc = SimpleNamespace(
			doctype="Leave Application",
			name="HR-LAP-0001",
			modified="2026-11-22 12:00:00",
			employee_name="Synthetic Employee",
			from_date="2026-12-01",
			to_date="2026-12-03",
			total_leave_days=3,
		)
		with (
			patch.object(ai_tools.leave, "pending_leave", return_value=doc),
			patch.object(ai_tools, "_", side_effect=lambda message: message),
		):
			preview = ai_tools.preview_approval(doc.name, doc.modified)
		self.assertEqual(
			preview["changes"],
			[
				{"fieldname": "status", "old": "Open", "new": "Approved"},
				{"fieldname": "docstatus", "old": 0, "new": 1},
			],
		)
		self.assertEqual(preview["details"], {"name": doc.name})
