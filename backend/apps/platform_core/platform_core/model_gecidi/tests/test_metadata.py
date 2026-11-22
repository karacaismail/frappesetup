"""Check the gateway's translation and AI write registration."""

import csv
import json
import runpy
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


class GatewayMetadataTests(unittest.TestCase):
	def test_every_gateway_doctype_field_has_a_description(self):
		definitions = sorted((APP_ROOT / "model_gecidi" / "doctype").glob("*/*.json"))
		self.assertTrue(definitions)
		for path in definitions:
			definition = json.loads(path.read_text(encoding="utf-8"))
			self.assertTrue(definition["fields"], definition["name"])
			for field in definition["fields"]:
				with self.subTest(doctype=definition["name"], fieldname=field["fieldname"]):
					description = field.get("description")
					self.assertIsInstance(description, str)
					self.assertTrue(description.strip())

	def test_turkish_translations_include_frappe_context_column(self):
		with (APP_ROOT / "translations" / "tr.csv").open(encoding="utf-8", newline="") as source:
			rows = list(csv.reader(source))
		self.assertTrue(rows)
		self.assertTrue(all(len(row) in (2, 3) for row in rows))
		keys = {(row[0], row[2] if len(row) == 3 else "") for row in rows}
		self.assertEqual(len(rows), len(keys))
		for label, context in (("Base URL", "AI API"), ("Enabled", "AI Route"), ("Route", "AI Usage Log")):
			self.assertIn((label, context), keys)
			self.assertNotIn((label, ""), keys)

	def test_sensitive_registry_doctypes_are_closed_to_general_ai_writes(self):
		hooks = runpy.run_path(str(APP_ROOT / "hooks.py"))
		self.assertTrue({"AI API", "AI Account"} <= set(hooks.get("ai_write_closed_doctypes", [])))
