"""The decision code ships as a package (AJA-230, architecture note AJA-213).

Expected rules:
- Frappe uses the package with `import atonota_login`. The code is not copied.
- `policy/actions.json` is package data. An installed package finds it without the source tree.
- `decision.py` stays free of Frappe. The Frappe link lives in `platform_core`.
"""

import ast
import json
import importlib.resources
import re
import unittest
from pathlib import Path

from atonota_login import decision

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "atonota_login"


def imported_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "__import__":
            names.add("__import__")
    return names


class PackagingTest(unittest.TestCase):
    def test_policy_file_is_package_data(self):
        self.assertEqual(decision.POLICY_FILE.parent.parent, PACKAGE)
        resource = importlib.resources.files("atonota_login") / "policy" / "actions.json"
        self.assertTrue(resource.is_file())

    def test_default_policy_is_read_from_the_package(self):
        resource = importlib.resources.files("atonota_login") / "policy" / "actions.json"
        self.assertEqual(decision.load_policy().version, decision.Policy(json.loads(resource.read_text("utf-8"))).version)

    def test_pyproject_declares_the_package_and_its_data(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^name = "atonota_login"$')
        self.assertRegex(text, r'(?m)^license = "MIT"$')
        # No runtime dependencies: the package is installed with --no-deps next to Frappe.
        self.assertRegex(text, r"(?m)^dependencies = \[\]$")
        self.assertIn('packages = ["atonota_login"]', text)
        self.assertTrue(re.search(r'atonota_login = \["policy/\*\.json"\]', text), text)

    def test_decision_has_no_frappe_import(self):
        names = imported_names(PACKAGE / "decision.py")
        self.assertNotIn("frappe", names)
        self.assertNotIn("__import__", names)


if __name__ == "__main__":
    unittest.main()
