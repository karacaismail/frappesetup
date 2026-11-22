"""Check the application catalog through Frappe's label translation."""

import json
from pathlib import Path
from unittest import TestCase

import frappe
from frappe.translate import get_translations_from_csv


class LabelTranslationTest(TestCase):
	def test_leave_balance_label_keeps_the_upstream_translation(self):
		path = Path(
			frappe.get_app_path("hrms", "hr", "doctype", "leave_application", "leave_application.json")
		)
		fields = json.loads(path.read_text(encoding="utf-8"))["fields"]
		label = next(field["label"] for field in fields if field["fieldname"] == "leave_balance")
		self.assertEqual(label, "Leave Balance Before Application")

		self.assertNotIn(label, get_translations_from_csv("tr", "hrms_tr"))
