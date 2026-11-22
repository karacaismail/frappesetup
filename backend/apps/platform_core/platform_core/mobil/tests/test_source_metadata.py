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

	def test_every_doctype_field_has_a_nonblank_description(self):
		self.assertTrue(DEFINITIONS)
		for path in DEFINITIONS:
			definition = json.loads(path.read_text(encoding="utf-8"))
			for field in definition["fields"]:
				with self.subTest(doctype=definition["name"], field=field["fieldname"]):
					description = field.get("description")
					self.assertIsInstance(description, str)
					self.assertTrue(description.strip())

	def test_doctype_field_text_uses_supported_translation_context(self):
		with (APP / "translations" / "tr.csv").open(encoding="utf-8", newline="") as source:
			rows = csv.reader(source, strict=True)
			translations = set()
			for row in rows:
				self.assertEqual(len(row), 3, f"tr.csv line {rows.line_num}: expected three columns")
				translations.add((row[0], row[2]))
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
