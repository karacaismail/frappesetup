"""Translations of the identity module (PROJE-KAYDI.md O-21 and O-23).

Expected behaviour (D-1):
- every user-visible message of the module is English in code and is translated with a context,
- the Turkish text is in `translations/tr.csv` with the same context (Frappe 16 CSV: source, text, context),
- no row of this module is context-free, so Frappe's own translations are never overridden,
- DocType labels and descriptions use the DocType name as context, as the desk does
  (frappe/public/js/frappe/form/controls/base_input.js:188 and :232).
"""

import ast
import csv
import os
import re

import frappe
from frappe.tests import IntegrationTestCase

CONTEXT = "platform_core.identity"
LINK = "PLT Identity Link"
DOCTYPES = (LINK, "Platform Identity Deletion")
APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY_SOURCES = ("identity", "api/auth.py", "api/identity.py", "api/__init__.py", "www/login.py")
TEMPLATE = os.path.join(APP, "www", "login.html")
# Only the DocType names are context-free: the desk translates them without a context, and Frappe has no such string.
CONTEXT_FREE_ALLOWED = set(DOCTYPES)


def _python_files():
	for item in PY_SOURCES:
		path = os.path.join(APP, item)
		if os.path.isfile(path):
			yield path
			continue
		for folder, _dirs, files in os.walk(path):
			if f"{os.sep}tests" in folder:
				continue
			yield from (os.path.join(folder, name) for name in files if name.endswith(".py"))


def _calls():
	"""(path, line, message, context) for every `_()` call in the module's Python code."""
	for path in _python_files():
		tree = ast.parse(open(path, encoding="utf-8").read())
		for node in ast.walk(tree):
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
				first = node.args[0] if node.args else None
				message = first.value if isinstance(first, ast.Constant) else None
				context = next(
					(
						k.value.value
						for k in node.keywords
						if k.arg == "context" and isinstance(k.value, ast.Constant)
					),
					None,
				)
				yield path, node.lineno, message, context


def _template_calls():
	text = open(TEMPLATE, encoding="utf-8").read()
	for match in re.finditer(r"_\((\"[^\"]*\"|'[^']*')\s*(,\s*context=(\"[^\"]*\"|'[^']*'))?\)", text):
		context = match.group(3)[1:-1] if match.group(3) else None
		yield TEMPLATE, text[: match.start()].count("\n") + 1, match.group(1)[1:-1], context


def _rows():
	with open(os.path.join(APP, "translations", "tr.csv"), encoding="utf-8", newline="") as handle:
		return [row for row in csv.reader(handle) if row]


class TestTranslations(IntegrationTestCase):
	def test_every_message_has_a_literal_text_and_the_module_context(self):
		problems = []
		for path, line, message, context in list(_calls()) + list(_template_calls()):
			where = f"{os.path.relpath(path, APP)}:{line}"
			if message is None:
				problems.append(f"{where}: message is not a literal string")
			elif context != CONTEXT:
				problems.append(f"{where}: context is {context!r} for {message!r}")
		self.assertEqual(problems, [])

	def test_every_message_has_a_turkish_row_with_the_same_context(self):
		rows = {(row[0], row[2] if len(row) > 2 else ""): row[1] for row in _rows()}
		missing = sorted(
			{message for _p, _l, message, _c in list(_calls()) + list(_template_calls()) if message}
			- {source for (source, context), text in rows.items() if context == CONTEXT and text.strip()}
		)
		self.assertEqual(missing, [])

	def test_module_rows_are_never_context_free(self):
		messages = {m for _p, _l, m, _c in list(_calls()) + list(_template_calls()) if m}
		for doctype in DOCTYPES:
			messages |= self._doctype_texts(doctype)
		context_free = sorted(
			row[0]
			for row in _rows()
			if row[0] in messages and (len(row) < 3 or not row[2]) and row[0] not in CONTEXT_FREE_ALLOWED
		)
		self.assertEqual(context_free, [])

	def test_doctype_labels_and_descriptions_are_translated_with_the_doctype_context(self):
		rows = {(row[0], row[2] if len(row) > 2 else ""): row[1] for row in _rows()}
		for doctype in DOCTYPES:
			texts = self._doctype_texts(doctype)
			missing = sorted(text for text in texts if not rows.get((text, doctype), "").strip())
			self.assertEqual(missing, [], doctype)
			self.assertTrue(rows.get((doctype, ""), "").strip(), f"DocType name {doctype}")

	def test_translation_is_used_at_runtime_and_frappe_strings_stay(self):
		frappe.local.lang = "tr"
		frappe.clear_cache()
		self.assertEqual(_t("Sign in with {0}").format("Atonota"), "Atonota ile oturum aç")
		self.assertEqual(_t("Password"), frappe._("Password", context=CONTEXT))
		# Frappe's own context-free translation is not replaced by a row of this module.
		own = {row[0] for row in _rows() if len(row) < 3 or not row[2]}
		self.assertNotIn("Password", own)
		self.assertNotIn("Sign in", own)
		frappe.local.lang = "en"

	@staticmethod
	def _doctype_texts(doctype: str) -> set[str]:
		meta = frappe.get_meta(doctype)
		texts = {meta.description} if meta.description else set()
		for field in meta.fields:
			texts |= {text for text in (field.label, field.description) if text}
			if field.fieldtype == "Select" and field.options:
				texts |= {option for option in field.options.split("\n") if option}
		return texts


def _t(message: str) -> str:
	return frappe._(message, context=CONTEXT)
