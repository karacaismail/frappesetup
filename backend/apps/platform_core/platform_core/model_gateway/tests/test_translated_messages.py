"""GILT step 5a: gateway messages and field labels reach the translation catalog."""

# ruff: noqa: RUF001

import ast
import unittest
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.model_gateway.doctype import validation

MAINTENANCE = Path(__file__).resolve().parents[1] / "maintenance.py"


def _is_translation(node) -> bool:
	return (
		isinstance(node, ast.Call)
		and isinstance(node.func, ast.Name)
		and node.func.id == "_"
		and len(node.args) == 1
		and isinstance(node.args[0], ast.Constant)
		and isinstance(node.args[0].value, str)
	)


class MaintenanceMessageTests(unittest.TestCase):
	def test_validation_errors_wrap_a_literal_message_in_translation(self):
		errors = [
			node
			for node in ast.walk(ast.parse(MAINTENANCE.read_text(encoding="utf-8")))
			if isinstance(node, ast.Call)
			and isinstance(node.func, ast.Attribute)
			and node.func.attr == "ValidationError"
			and node.args
		]
		self.assertTrue(errors)
		untranslated = [ast.unparse(node) for node in errors if not _is_translation(node.args[0])]
		self.assertEqual(untranslated, [])


class LabelContextTests(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		previous = frappe.local.lang
		frappe.local.lang = "tr"
		self.addCleanup(setattr, frappe.local, "lang", previous)

	def test_url_label_uses_the_doctype_context(self):
		# tr.csv stores "Base URL" only with the "PLT AI API" context, like every DocType label.
		with self.assertRaises(frappe.ValidationError) as raised:
			validation.validate_url("not a url", "Base URL", "PLT AI API")
		self.assertIn("Bağlantı Adresi", str(raised.exception))
		self.assertNotIn("Base URL", str(raised.exception))

	def test_identifier_label_falls_back_to_a_context_free_row(self):
		# Frappe tries "<label>:<doctype>" first, then "<label>" (frappe/utils/translations.py).
		with self.assertRaises(frappe.ValidationError) as raised:
			validation.encode_identifiers('["a", "a"]', "Allowed Models", "PLT AI API")
		self.assertIn("İzinli Modeller", str(raised.exception))
