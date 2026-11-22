"""Check the shipped Mobile DocType definitions and translation sources."""

import csv
import json
import unittest
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
DEFINITIONS = sorted((APP / "mobil" / "doctype").glob("*/*.json"))


class MobileSourceMetadataTest(unittest.TestCase):
	def test_doctype_definitions_follow_frappe_export_format(self):
		self.assertTrue(DEFINITIONS)
		for path in DEFINITIONS:
			with self.subTest(doctype=path.stem):
				source = path.read_text(encoding="utf-8")
				definition = json.loads(source)
				self.assertEqual(source, json.dumps(definition, indent=1, sort_keys=True) + "\n")
				self.assertIsInstance(datetime.fromisoformat(definition["modified"]), datetime)

	def test_doctype_field_text_uses_supported_translation_context(self):
		with (APP / "translations" / "tr.csv").open(encoding="utf-8", newline="") as source:
			translations = {(row[0], row[2] if len(row) == 3 else "") for row in csv.reader(source)}
		for path in DEFINITIONS:
			definition = json.loads(path.read_text(encoding="utf-8"))
			name = definition["name"]
			texts = [name, definition["description"]]
			for field in definition["fields"]:
				texts.extend((field["label"], field["description"]))
				if field["fieldtype"] == "Select":
					texts.extend(field["options"].splitlines())
			for text in texts:
				with self.subTest(doctype=name, source=text):
					self.assertTrue((text, name) in translations or (text, "") in translations)
