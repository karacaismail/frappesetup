"""Check the application catalog through Frappe's label translation."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.translate import get_translations_from_csv


class LabelTranslationTest(TestCase):
	def test_leave_balance_label_uses_the_selected_language(self):
		path = Path(
			frappe.get_app_path("hrms", "hr", "doctype", "leave_application", "leave_application.json")
		)
		fields = json.loads(path.read_text(encoding="utf-8"))["fields"]
		label = next(field["label"] for field in fields if field["fieldname"] == "leave_balance")
		self.assertEqual(label, "Leave Balance Before Application")

		with patch("frappe.translate.get_all_translations") as catalog:
			catalog.side_effect = lambda lang: get_translations_from_csv(lang, "hrms_tr")
			for locale, expected in (
				("tr", "Talep Öncesi İzin Bakiyesi"),
				("en", "Leave Balance Before Application"),
			):
				with self.subTest(locale=locale), patch.object(frappe, "local", SimpleNamespace(lang=locale)):
					self.assertEqual(frappe._(label), expected)
