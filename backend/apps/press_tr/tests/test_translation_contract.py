"""Check that Press translations are scoped to their source."""

import ast
import csv
import json
import re
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "press_tr"


class TranslationContractTest(unittest.TestCase):
	def setUp(self):
		with (APP / "translations/tr.csv").open(encoding="utf-8", newline="") as source:
			self.rows = list(csv.reader(source))

	def test_translations_have_unique_contextual_keys(self):
		self.assertTrue(all(len(row) == 3 and all(row) for row in self.rows))
		keys = [(source, context) for source, _, context in self.rows]
		self.assertEqual(len(keys), len(set(keys)))

	def test_missing_anonymization_key_error_is_translated(self):
		message = "Configure a stable site key for Press anonymization."
		tree = ast.parse((APP / "kimlik/identity.py").read_text())
		key_error = next(
			node.exc
			for node in ast.walk(tree)
			if isinstance(node, ast.Raise)
			and isinstance(node.exc, ast.Call)
			and isinstance(node.exc.func, ast.Name)
			and node.exc.func.id == "ServiceUnavailable"
		)
		self.assertEqual(ast.unparse(key_error.args[0]), f"_({message!r}, context='press_tr')")
		self.assertIn((message, "press_tr"), {(row[0], row[2]) for row in self.rows})

	def test_doctype_descriptions_and_labels_have_form_context(self):
		keys = {(row[0], row[2]) for row in self.rows if len(row) == 3}
		for path in (APP / "kimlik/doctype").glob("*/*.json"):
			doc = json.loads(path.read_text())
			texts = [doc["description"]]
			for field in doc["fields"]:
				texts.extend((field["label"], field["description"]))
			for source in texts:
				with self.subTest(source=source, doctype=doc["name"]):
					self.assertIn((source, doc["name"]), keys)

	def test_contextual_messages_have_turkish_translations(self):
		keys = {(row[0], row[2]) for row in self.rows if len(row) == 3}
		for path in APP.rglob("*.py"):
			for node in ast.walk(ast.parse(path.read_text())):
				if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
					continue
				if node.func.id != "_" or not isinstance(node.args[0], ast.Constant):
					continue
				# Frappe owns this lookup for matching its generated audit comment.
				if node.args[0].value == "renamed from {0} to {1}":
					continue
				with self.subTest(path=path.name, source=node.args[0].value):
					context = next((arg.value.value for arg in node.keywords if arg.arg == "context"), None)
					self.assertIn((node.args[0].value, context), keys)

	def test_openapi_prose_has_turkish_translations(self):
		path = APP.parents[2] / "contracts/press_tr.openapi.yaml"
		if not path.exists():
			path = APP.parent / "tests/press_tr.openapi.yaml"
		keys = {(row[0], row[2]) for row in self.rows if len(row) == 3}
		for source in re.findall(r"^ +(?:summary|description): (.+)$", path.read_text(), re.MULTILINE):
			with self.subTest(source=source):
				self.assertIn((source, "press_tr.openapi"), keys)


class GuestRateLimitContractTest(unittest.TestCase):
	def test_login_callback_has_a_request_limit(self):
		tree = ast.parse((APP / "api/auth.py").read_text())
		callback = next(
			node
			for node in tree.body
			if isinstance(node, ast.FunctionDef) and node.name == "keycloak_callback"
		)
		self.assertTrue(
			any(
				isinstance(decorator, ast.Call)
				and isinstance(decorator.func, ast.Name)
				and decorator.func.id == "rate_limit"
				for decorator in callback.decorator_list
			)
		)
