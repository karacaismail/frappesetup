"""Gate: every Frappe list query in the app code is bounded or explains why not (P-1, P-3).

`frappe.get_all` reads every matching row when no limit is given. A table that
grows can then make one request read the whole table. The gate scans the app
code under backend/apps, without tests, and finds each call of
`frappe.get_all`, `frappe.get_list`, `frappe.db.get_all` and
`frappe.db.get_list` (AJA-1330).

A call passes when it sets `limit`, `limit_page_length` or `page_length` to a
value other than 0 or None. Any other call needs a reason comment. The comment
starts with `# list-limit:` and sits on the call line or on the comment lines
directly above the statement. Example:

    # list-limit: the help topics are a small settings table.
    topics = frappe.get_all(TOPIC, fields=TOPIC_FIELDS)

Run without Frappe:

    python3.14 -B -m unittest backend/dev/tests/test_list_query_limits.py
"""

import ast
import tempfile
import unittest
from pathlib import Path

APPS = Path(__file__).resolve().parents[2] / "apps"
MARKER = "# list-limit:"
LIMIT_KEYWORDS = {"limit", "limit_page_length", "page_length"}
LIST_FUNCTIONS = {"get_all", "get_list"}
# Files whose lists are fixed in their own task. Remove an entry when that task's branch is merged.
PENDING = {
    "hrms_tr/hrms_tr/home_summary.py": "AJA-1328",
    "platform_core/platform_core/reseller/customers.py": "AJA-1328",
    "platform_core/platform_core/model_gateway/large_file.py": "AJA-1329",
}


def _is_frappe_list_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in LIST_FUNCTIONS:
        return False
    owner = func.value
    if isinstance(owner, ast.Name):
        return owner.id == "frappe"
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "db"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "frappe"
    )


def _has_limit(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg not in LIMIT_KEYWORDS:
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and value.value in (0, None):
            return False
        return True
    return False


def _has_reason(lines: list[str], call: ast.Call, statement_line: int) -> bool:
    if MARKER in lines[call.lineno - 1]:
        return True
    index = statement_line - 2
    while index >= 0 and lines[index].strip().startswith("#"):
        if lines[index].strip().startswith(MARKER) and lines[index].strip() != MARKER:
            return True
        index -= 1
    return False


def unbounded_calls(source: str) -> list[int]:
    """Line numbers of list calls with no limit and no reason comment."""
    tree = ast.parse(source)
    lines = source.splitlines()
    found = []
    for statement in ast.walk(tree):
        if not isinstance(statement, ast.stmt):
            continue
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.stmt):
                continue
            for node in ast.walk(child):
                if isinstance(node, ast.Call) and _is_frappe_list_call(node):
                    if not _has_limit(node) and not _has_reason(lines, node, statement.lineno):
                        found.append(node.lineno)
    return sorted(set(found))


def app_files(root: Path = APPS) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if any(part in ("tests", "test") for part in parts) or path.name.startswith("test_"):
            continue
        files.append(path)
    return files


def gate_problems(root: Path = APPS, pending: dict | None = None) -> list[str]:
    """Every unexplained unbounded list call under root, as path:line. Pending files are skipped."""
    problems = []
    for path in app_files(root):
        if path.relative_to(root).as_posix() in (pending or {}):
            continue
        for line in unbounded_calls(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(root)}:{line}")
    return problems


class ListQueryLimitTest(unittest.TestCase):
    def test_app_code_has_no_unexplained_unbounded_list(self):
        message = "Set a limit or add a '# list-limit: <reason>' comment above the call."
        self.assertEqual(gate_problems(pending=PENDING), [], message)

    def test_scan_finds_app_files(self):
        self.assertGreater(len(app_files()), 50)

    def test_pending_files_exist(self):
        for name in PENDING:
            self.assertTrue((APPS / name).is_file(), name)


class DetectorTest(unittest.TestCase):
    def test_call_without_limit_is_caught(self):
        self.assertEqual(unbounded_calls("import frappe\nrows = frappe.get_all('ToDo')\n"), [2])

    def test_db_and_get_list_forms_are_caught(self):
        source = "import frappe\na = frappe.db.get_all('ToDo')\nb = frappe.get_list('ToDo')\n"
        self.assertEqual(unbounded_calls(source), [2, 3])

    def test_zero_and_none_limits_are_caught(self):
        source = (
            "import frappe\n"
            "a = frappe.get_all('ToDo', limit=0)\n"
            "b = frappe.get_all('ToDo', limit_page_length=0)\n"
            "c = frappe.get_all('ToDo', limit=None)\n"
        )
        self.assertEqual(unbounded_calls(source), [2, 3, 4])

    def test_multiline_call_in_loop_is_caught(self):
        source = "import frappe\nfor row in frappe.get_all(\n\t'ToDo',\n\tfields=['name'],\n):\n\tpass\n"
        self.assertEqual(unbounded_calls(source), [2])

    def test_limit_passes(self):
        source = (
            "import frappe\n"
            "a = frappe.get_all('ToDo', limit=10)\n"
            "b = frappe.get_all('ToDo', limit_page_length=SIZE)\n"
            "c = frappe.get_list('ToDo', page_length=5)\n"
        )
        self.assertEqual(unbounded_calls(source), [])

    def test_reason_comment_passes(self):
        source = (
            "import frappe\n"
            "# list-limit: a small settings table.\n"
            "rows = frappe.get_all(\n"
            "\t'ToDo',\n"
            ")\n"
            "other = frappe.get_all('ToDo')  # list-limit: one row per role.\n"
        )
        self.assertEqual(unbounded_calls(source), [])

    def test_empty_reason_and_far_comment_fail(self):
        source = (
            "import frappe\n"
            "# list-limit:\n"
            "a = frappe.get_all('ToDo')\n"
            "# list-limit: far away.\n"
            "x = 1\n"
            "b = frappe.get_all('ToDo')\n"
        )
        self.assertEqual(unbounded_calls(source), [3, 6])

    def test_other_get_all_is_ignored(self):
        self.assertEqual(unbounded_calls("cookies = headers.get_all('Set-Cookie', [])\n"), [])

    def test_new_file_without_reason_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app" / "tests").mkdir(parents=True)
            (root / "app" / "new_module.py").write_text(
                "import frappe\nrows = frappe.get_all('ToDo')\n", encoding="utf-8"
            )
            (root / "app" / "tests" / "helper.py").write_text(
                "import frappe\nrows = frappe.get_all('ToDo')\n", encoding="utf-8"
            )
            self.assertEqual(gate_problems(root), ["app/new_module.py:2"])


if __name__ == "__main__":
    unittest.main()
