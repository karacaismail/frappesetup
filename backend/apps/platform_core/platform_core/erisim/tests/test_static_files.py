"""Checks on the engine's files that are not Python: the contract and the translation rows.

These tests read files only. They run without a site:
`python -m unittest discover -s <this folder> -p test_static_files.py`.
The contract lives outside the app. Inside a bench it is not there and those tests are skipped.
"""

import ast
import csv
import os
import re
import sys
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve()
CONTRACT_NAME = "platform_core-erisim.openapi.yaml"
# The longest sentence the plain-language rule allows in an explanation.
MAX_WORDS = 15


def contract_path() -> Path | None:
	given = os.environ.get("ACCESS_TEST_OPENAPI")
	if given:
		return Path(given)
	for parent in HERE.parents:
		candidate = parent / "contracts" / CONTRACT_NAME
		if candidate.is_file():
			return candidate
	return None


def strings_only(node, trail: str, found: list[str]) -> None:
	"""Collect list items that YAML read as a mapping although the list holds sentences."""
	if isinstance(node, dict):
		for key, value in node.items():
			strings_only(value, f"{trail}.{key}", found)
	elif isinstance(node, list) and any(isinstance(item, str) for item in node):
		found += [f"{trail}[{index}]" for index, item in enumerate(node) if not isinstance(item, str)]
	elif isinstance(node, list):
		for index, item in enumerate(node):
			strings_only(item, f"{trail}[{index}]", found)


class TestContractFile(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		path = contract_path()
		if path is None:
			raise unittest.SkipTest("The contract file is outside the app and is not mounted here.")
		cls.contract = yaml.safe_load(path.read_text(encoding="utf-8"))

	def test_sentence_lists_hold_only_text(self):
		"""An unquoted sentence with `: ` in it becomes a mapping and silently drops out of the list."""
		found: list[str] = []
		for section in ("x-report-rules", "x-replaced-endpoints", "x-hooks", "x-ai-tools"):
			strings_only(self.contract.get(section), section, found)

		self.assertEqual(found, [])

	def test_no_hand_kept_copy_of_a_replaced_frappe_address(self):
		"""The replaced address is written once, in `x-frappe-original` of the engine operation."""
		copies = [path for path in self.contract["paths"] if path.startswith("/frappe.")]

		self.assertEqual(copies, [])
		originals = {
			original
			for item in self.contract["paths"].values()
			for operation in item.values()
			if isinstance(operation, dict)
			for original in operation.get("x-frappe-original", [])
		}
		self.assertLessEqual(
			{"frappe.desk.search.search_link", "frappe.desk.search.search_widget"}, originals
		)

	def test_optional_text_fields_of_a_rule_may_be_null(self):
		"""Frappe returns `null` for an empty text field, for example `match_field` of an `all` rule."""
		properties = self.contract["components"]["schemas"]["AccessRule"]["properties"]
		for field in ("match_field", "filters", "description"):
			with self.subTest(field=field):
				self.assertIn("null", properties[field]["type"])

	def test_every_removed_hook_is_listed(self):
		removed = {row["name"] for row in self.contract["x-hooks"]["removed"]}

		self.assertLessEqual(
			{"access_rule_report_scopes", "access_rule_aware_reports", "access_rule_allowed_queries"},
			removed,
		)


class TestTranslationRows(unittest.TestCase):
	def engine_rows(self) -> list[list[str]]:
		app = next(parent for parent in HERE.parents if (parent / "translations" / "tr.csv").is_file())
		code = ""
		files = [
			*(app / "erisim").rglob("*.py"),
			*(app / "erisim").rglob("*.json"),
			app / "api" / "access.py",
		]
		for path in files:
			if "tests" not in path.parts and not path.name.startswith("test_"):
				# Join string literals that continue on the next line.
				code += re.sub(r'"\s*\n\s*"', "", path.read_text(encoding="utf-8")).replace('\\"', '"')
		with (app / "translations" / "tr.csv").open(newline="", encoding="utf-8") as handle:
			rows = list(csv.reader(handle))
		return [row for row in rows if (len(row) > 2 and row[2] == "Access Rule") or f'"{row[0]}"' in code]

	def test_turkish_text_uses_short_sentences(self):
		rows = self.engine_rows()
		self.assertGreater(len(rows), 70)
		long_ones = [
			sentence
			for row in rows
			for sentence in re.split(r"(?<=[.!?:])\s+", row[1])
			if len(sentence.split()) > MAX_WORDS
		]

		self.assertEqual(long_ones, [])


APP = next(parent for parent in HERE.parents if (parent / "translations" / "tr.csv").is_file())
# Reads and writes that do not check the permission of the user (G-3, G-5, V-1).
UNCHECKED = {"get_all", "get_value", "set_value"}
SEMGREP_RULE = re.compile(r"#\s*nosemgrep: [a-z][a-z0-9.-]*-[a-z0-9-]+(\s|$)")


def engine_files(tests: bool) -> list[Path]:
	files = [*(APP / "erisim").rglob("*.py"), APP / "api" / "access.py", APP / "api" / "test_access.py"]
	return [path for path in files if ("tests" in path.parts or path.name.startswith("test_")) == tests]


def is_frappe_call(node: ast.AST, names: set[str]) -> bool:
	return (
		isinstance(node, ast.Call)
		and isinstance(node.func, ast.Attribute)
		and node.func.attr in names
		and ast.unparse(node.func).startswith("frappe.")
	)


class TestEngineCode(unittest.TestCase):
	def test_every_unchecked_read_or_write_says_why(self):
		"""A call that skips the permission check needs its reason in a comment right above it."""
		missing = []
		for path in engine_files(tests=False):
			lines = path.read_text(encoding="utf-8").splitlines()
			for node in ast.walk(ast.parse("\n".join(lines))):
				if not is_frappe_call(node, UNCHECKED):
					continue
				above = lines[max(node.lineno - 4, 0) : node.lineno]
				if not any(line.strip().startswith("#") or "  # " in line for line in above):
					missing.append(f"{path.relative_to(APP)}:{node.lineno}")

		self.assertEqual(missing, [])

	def test_every_list_read_states_its_limit(self):
		"""`frappe.get_all` without a limit reads everything. The choice must be written down (P-3)."""
		missing = [
			f"{path.relative_to(APP)}:{node.lineno}"
			for path in engine_files(tests=False)
			for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
			if is_frappe_call(node, {"get_all", "get_list"})
			and not {keyword.arg for keyword in node.keywords} & {"limit", "limit_page_length"}
		]

		self.assertEqual(missing, [])

	def test_every_suppressed_finding_names_its_rule(self):
		"""`nosemgrep` without a rule name hides every rule on the line (R-2)."""
		missing = [
			f"{path.relative_to(APP)}:{number}"
			for path in [*engine_files(tests=True), *engine_files(tests=False)]
			for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
			if "nosemgrep" in line and path != HERE and not SEMGREP_RULE.search(line)
		]

		self.assertEqual(missing, [])


# Every place outside the engine that names an engine path which is not its public module (B-6).
# A change to one of these paths must be checked against the file next to it.
KNOWN_INTERNAL_USERS = {
	# The shell allows a Website User to call the guarded search and must name the replacement.
	("kabuk/native_metadata.py", "platform_core.erisim.link_search.search_link"),
}
ENGINE_PATH = re.compile(r"platform_core\.erisim(?:\.\w+)+")


class TestWhoUsesTheEngine(unittest.TestCase):
	def test_other_modules_use_only_the_public_module(self):
		"""Other modules call `platform_core.erisim.api`. Anything else must be listed above."""
		found = set()
		for path in APP.rglob("*.py"):
			relative = path.relative_to(APP).as_posix()
			# `hooks.py` binds the engine to Frappe; `api/access.py` holds the engine's own endpoints.
			if relative.startswith("erisim/") or relative in (
				"hooks.py",
				"api/access.py",
				"api/test_access.py",
			):
				continue
			for reference in ENGINE_PATH.findall(path.read_text(encoding="utf-8")):
				if not reference.startswith("platform_core.erisim.api"):
					found.add((relative, reference))

		self.assertEqual(found, KNOWN_INTERNAL_USERS)


class TestDeclaredPackages(unittest.TestCase):
	def test_every_third_party_import_is_declared(self):
		"""T-3: a package the code imports is declared, also when Frappe installs it anyway."""
		project = (APP.parent / "pyproject.toml").read_text(encoding="utf-8")
		block = project[
			project.index("dependencies = [") : project.index("]", project.index("dependencies = ["))
		]
		declared = {name.lower() for name in re.findall(r'"([A-Za-z0-9_.-]+)', block)}
		ours = {"frappe", "platform_core", "erpnext"}
		imported = set()
		for path in engine_files(tests=False):
			for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
				names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
				if isinstance(node, ast.ImportFrom) and node.module and not node.level:
					names = [node.module]
				imported |= {name.split(".")[0] for name in names}
		third_party = {name for name in imported if name not in sys.stdlib_module_names and name not in ours}

		self.assertGreater(len(third_party), 0)
		self.assertEqual({name for name in third_party if name.lower() not in declared}, set())
