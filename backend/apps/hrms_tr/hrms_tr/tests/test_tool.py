"""HRMS TR's app declaration exposes the approval only as a write tool."""

import unittest

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
