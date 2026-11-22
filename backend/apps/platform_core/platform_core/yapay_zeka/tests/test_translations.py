"""Translations of the AI access layer (PROJE-KAYDI.md O-21 and O-23).

Expected behaviour (D-1):
- every user-visible message of the layer is English in code and is translated with a context,
- the Turkish text is in `translations/tr.csv` with the same context (Frappe 16 CSV: source, text, context),
- no row of this layer is context-free, except the two DocType names, so Frappe's own translations
  are never overridden,
- DocType labels and descriptions use the DocType name as context, as the desk does,
- the layer's Python code, DocType files and contract carry no Turkish letters.
"""

import ast
import csv
import re
from pathlib import Path

import frappe

import platform_core
from platform_core.yapay_zeka.errors import CONTEXT
from platform_core.yapay_zeka.tests.base import YzTestCase

APP = Path(platform_core.__file__).parent
LAYER = APP / "yapay_zeka"
DOCTYPES = ("AI Action Log", "AI Action Proposal")
# Turkish letters, written as code points so that this file passes its own check.
TURKISH_CODE_POINTS = (231, 287, 305, 304, 246, 351, 252, 199, 286, 214, 350, 220, 226)
TURKISH_LETTERS = re.compile("[" + "".join(map(chr, TURKISH_CODE_POINTS)) + "]")
PLACEHOLDER = re.compile(r"\{\d+\}")


def layer_sources() -> list[Path]:
	files = [path for path in LAYER.rglob("*.py") if "tests" not in path.relative_to(LAYER).parts]
	return sorted([*files, APP / "api" / "ai.py"])


def message_calls() -> list[tuple[Path, int, str | None, str | None]]:
	"""(path, line, message, name of the context argument) for every `_()` call of the layer."""
	found = []
	for path in layer_sources():
		for node in ast.walk(ast.parse(path.read_text())):
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
				first = node.args[0] if node.args else None
				message = first.value if isinstance(first, ast.Constant) else None
				context = next(
					(
						kw.value.id
						for kw in node.keywords
						if kw.arg == "context" and isinstance(kw.value, ast.Name)
					),
					None,
				)
				found.append((path, node.lineno, message, context))
	return found


def rows() -> list[list[str]]:
	with open(APP / "translations" / "tr.csv", encoding="utf-8", newline="") as handle:
		return [row for row in csv.reader(handle) if row]


class TestTranslations(YzTestCase):
	def test_every_message_is_a_literal_with_the_layer_context(self):
		calls = message_calls()

		self.assertGreater(len(calls), 70)
		for path, line, message, context in calls:
			self.assertIsInstance(message, str, f"{path.name}:{line}")
			self.assertEqual(context, "CONTEXT", f"{path.name}:{line}")

	def test_every_message_has_a_turkish_row_with_the_same_context(self):
		translated = {row[0]: row[1] for row in rows() if len(row) == 3 and row[2] == CONTEXT}

		for path, line, message, _context in message_calls():
			self.assertIn(message, translated, f"{path.name}:{line}")
			text = translated[message]
			self.assertTrue(text.strip() and text != message, message)
			self.assertEqual(sorted(PLACEHOLDER.findall(text)), sorted(PLACEHOLDER.findall(message)), message)

	def test_no_row_of_the_layer_is_left_without_a_use(self):
		used = {message for _path, _line, message, _context in message_calls()}
		unused = [row[0] for row in rows() if len(row) == 3 and row[2] == CONTEXT and row[0] not in used]

		self.assertEqual(unused, [])

	def test_labels_and_descriptions_are_translated_with_the_doctype_as_context(self):
		table = {(row[0], row[2]): row[1] for row in rows() if len(row) == 3}

		for doctype in DOCTYPES:
			meta = frappe.get_meta(doctype)
			texts = [
				meta.description,
				*(text for field in meta.fields for text in (field.label, field.description)),
			]
			for text in texts:
				self.assertTrue(table.get((text, doctype), "").strip(), f"{doctype}: {text}")
			self.assertTrue(table.get((doctype, ""), "").strip(), doctype)

	def test_only_the_doctype_names_are_context_free(self):
		mine = {message for _path, _line, message, _context in message_calls()}
		labels = {
			text
			for doctype in DOCTYPES
			for field in frappe.get_meta(doctype).fields
			for text in (field.label, field.description)
		}
		context_free = [row[0] for row in rows() if len(row) < 3 or not row[2]]

		self.assertEqual(sorted(set(context_free) & (mine | labels)), [])
		self.assertLessEqual(set(DOCTYPES), set(context_free))

	def test_a_message_reaches_the_user_in_turkish(self):
		frappe.clear_cache()
		original = frappe.local.lang
		frappe.local.lang = "tr"
		try:
			text = frappe._("Proposal not found.", context=CONTEXT)
		finally:
			frappe.local.lang = original

		self.assertEqual(
			text, dict((row[0], row[1]) for row in rows() if row[2] == CONTEXT)["Proposal not found."]
		)

	def test_source_text_of_the_layer_carries_no_turkish_letters(self):
		contract = APP.parents[2] / "contracts" / "platform_core-yapay-zeka.openapi.yaml"
		files = [
			*LAYER.rglob("*.py"),
			*LAYER.rglob("*.json"),
			APP / "api" / "ai.py",
			APP / "api" / "test_ai.py",
		]
		if contract.exists():
			files.append(contract)
		offenders = [
			f"{path.name}:{number}"
			for path in sorted(files)
			for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
			if TURKISH_LETTERS.search(line)
		]

		self.assertEqual(offenders, [])
