"""Visible text of the access rule engine is English in the source and Turkish in `tr.csv` (O-21).

The translation file is `platform_core/translations/tr.csv`. Its columns are source,
translation and context (O-23). Field labels of the Access Rule document type carry the
document type name as context, because short labels such as "Scope" mean other things elsewhere.
"""

# The expected Turkish text below is test data. Ruff reads the Turkish dotless i as a typo.
# ruff: noqa: RUF001
import ast
import csv
import json
from pathlib import Path

import frappe

import platform_core
from platform_core.erisim import ai_tools
from platform_core.erisim.tests.base import DOCTYPE, EMPLOYEE_1, EMPLOYEE_2, RULE_DOCTYPE, ErisimTestCase

ROOT = Path(platform_core.__file__).parent
CSV_PATH = ROOT / "translations" / "tr.csv"
TURKISH_LETTERS = set("çğıöşüÇĞİÖŞÜ")


def doctype_strings() -> dict[str, tuple[set[str], set[str]]]:
	"""Labels and descriptions of every document type of the engine, keyed by document type name."""
	found = {}
	for path in sorted((ROOT / "erisim" / "doctype").glob("*/*.json")):
		definition = json.loads(path.read_text())
		labels = {definition["name"]}
		descriptions = {definition["description"]}
		for field in definition["fields"]:
			if field.get("label"):
				labels.add(field["label"])
			if field.get("description"):
				descriptions.add(field["description"])
		found[definition["name"]] = (labels, descriptions)
	return found


def message_strings() -> set[str]:
	"""Every text passed to `_()` in the engine's code, tests excluded."""
	files = [
		*(ROOT / "erisim").glob("*.py"),
		*(ROOT / "erisim" / "doctype").rglob("*.py"),
		ROOT / "api" / "access.py",
	]
	messages = set()
	for path in files:
		if path.name.startswith("test_"):
			continue
		for node in ast.walk(ast.parse(path.read_text())):
			if (
				isinstance(node, ast.Call)
				and isinstance(node.func, ast.Name)
				and node.func.id == "_"
				and node.args
				and isinstance(node.args[0], ast.Constant)
			):
				messages.add(node.args[0].value)
	return messages


def tool_strings() -> set[str]:
	return {declaration["description"] for declaration in ai_tools.declare()}


def csv_rows() -> dict[tuple[str, str], str]:
	"""Rows of the translation file keyed by (source, context)."""
	if not CSV_PATH.exists():
		return {}
	rows = {}
	with CSV_PATH.open(newline="", encoding="utf-8") as handle:
		for row in csv.reader(handle):
			if len(row) >= 2:
				rows[(row[0], row[2] if len(row) > 2 else "")] = row[1]
	return rows


class TestTranslations(ErisimTestCase):
	def all_visible(self) -> set[str]:
		visible = message_strings() | tool_strings()
		for labels, descriptions in doctype_strings().values():
			visible |= labels | descriptions
		return visible

	def test_source_text_is_english(self):
		for text in sorted(self.all_visible()):
			with self.subTest(text=text[:60]):
				self.assertFalse(TURKISH_LETTERS & set(text), text)
				self.assertTrue(text.isascii(), text)

	def test_every_visible_text_has_a_turkish_row(self):
		rows = csv_rows()
		expected = {(text, "") for text in message_strings() | tool_strings()}
		for doctype, (labels, descriptions) in doctype_strings().items():
			expected |= {(text, doctype) for text in labels | descriptions}
		for source, context in sorted(expected):
			with self.subTest(source=source[:60]):
				translation = rows.get((source, context), "")
				self.assertTrue(translation.strip(), f"no Turkish row for: {source}")
				self.assertNotEqual(translation, source)

	def test_translations_keep_the_placeholders(self):
		for (source, _context), translation in csv_rows().items():
			for placeholder in ("{0}", "{1}"):
				self.assertEqual(source.count(placeholder), translation.count(placeholder), source)

	def test_label_is_turkish_in_turkish_and_english_in_english(self):
		for label, turkish in (
			("Match Field", "Eşleşme Alanı"),
			("Scope", "Kapsam"),
			("Allow Read", "Okumaya İzin Ver"),
		):
			with self.subTest(label=label):
				self.assertEqual(frappe._(label, lang="tr", context=RULE_DOCTYPE), turkish)
				self.assertEqual(frappe._(label, lang="en", context=RULE_DOCTYPE), label)

	def test_document_type_label_follows_the_language(self):
		previous = frappe.local.lang
		self.addCleanup(setattr, frappe.local, "lang", previous)

		frappe.local.lang = "tr"
		turkish = frappe.get_meta(RULE_DOCTYPE).get_translated_label("match_field")
		frappe.local.lang = "en"
		english = frappe.get_meta(RULE_DOCTYPE).get_translated_label("match_field")

		self.assertEqual((turkish, english), ("Eşleşme Alanı", "Match Field"))

	def test_error_message_follows_the_users_language(self):
		message = "Only a System Manager can explain another user's permission."
		turkish = "Başka kullanıcının iznini yalnız System Manager açıklayabilir."
		query = {"doctype": DOCTYPE, "name": self.records[EMPLOYEE_1], "user": EMPLOYEE_2}
		self.addCleanup(self.set_language, EMPLOYEE_1, "en")

		self.set_language(EMPLOYEE_1, "tr")
		in_turkish = self.api(self.login(EMPLOYEE_1), "GET", "explain_permission", query=query)
		self.set_language(EMPLOYEE_1, "en")
		in_english = self.api(self.login(EMPLOYEE_1), "GET", "explain_permission", query=query)

		self.assertEqual((in_turkish.status_code, in_english.status_code), (403, 403))
		self.assertIn(turkish, json.dumps(in_turkish.json, ensure_ascii=False))
		self.assertIn(message, json.dumps(in_english.json, ensure_ascii=False))
		self.assertNotIn(turkish, json.dumps(in_english.json, ensure_ascii=False))

	def set_language(self, user: str, language: str) -> None:
		frappe.set_user("Administrator")
		frappe.db.set_value("User", user, "language", language)
		frappe.clear_cache(user=user)
		frappe.db.commit()  # nosemgrep: the request uses another connection
