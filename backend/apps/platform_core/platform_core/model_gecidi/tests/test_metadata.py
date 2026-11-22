"""Check the gateway's translation and AI write registration."""

import csv
import runpy
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


class GatewayMetadataTests(unittest.TestCase):
	def test_turkish_translations_include_frappe_context_column(self):
		with (APP_ROOT / "translations" / "tr.csv").open(encoding="utf-8", newline="") as source:
			rows = list(csv.reader(source))
		self.assertTrue(rows)
		self.assertTrue(all(len(row) == 3 for row in rows))
		self.assertEqual(len(rows), len({(key, context) for key, _, context in rows}))

	def test_sensitive_registry_doctypes_are_closed_to_general_ai_writes(self):
		hooks = runpy.run_path(str(APP_ROOT / "hooks.py"))
		self.assertTrue({"AI API", "AI Account"} <= set(hooks.get("ai_write_closed_doctypes", [])))
