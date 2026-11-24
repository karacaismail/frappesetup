"""Check the application catalog through Frappe's label translation."""

import ast
import csv
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


APP = Path(__file__).resolve().parents[1]
CONTEXT = "hrms_tr"
# Frappe core owns these strings. The context-qualified lookup falls back to its translation.
CORE_MESSAGES = {"Status", "Document Status", "Not permitted"}


def _calls():
	for path in sorted(APP.rglob("*.py")):
		if "tests" in path.relative_to(APP).parts or path.name.startswith("test_"):
			continue
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
				yield path.relative_to(APP), node


def _rows():
	with (APP / "translations" / "tr.csv").open(encoding="utf-8", newline="") as source:
		return [row for row in csv.reader(source) if row]


class MessageContextTest(TestCase):
	def test_every_message_is_a_literal_with_the_app_context(self):
		problems = []
		for path, node in _calls():
			literal = len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
			context = next(
				(
					word.value.value
					for word in node.keywords
					if word.arg == "context" and isinstance(word.value, ast.Constant)
				),
				None,
			)
			if not literal or context != CONTEXT:
				problems.append(f"{path}:{node.lineno}: {ast.unparse(node)}")
		self.assertEqual(problems, [])

	def test_app_messages_have_a_turkish_row_with_the_app_context(self):
		keys = {(row[0], row[2] if len(row) > 2 else "") for row in _rows() if row[1].strip()}
		messages = {
			node.args[0].value
			for _path, node in _calls()
			if node.args and isinstance(node.args[0], ast.Constant)
		}
		self.assertTrue(messages)
		missing = sorted(message for message in messages - CORE_MESSAGES if (message, CONTEXT) not in keys)
		self.assertEqual(missing, [])
		context_free = sorted(
			row[0] for row in _rows() if row[0] in messages and (len(row) < 3 or not row[2])
		)
		self.assertEqual(context_free, [])
