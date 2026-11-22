"""Use the shared checker for the Press identity module and its entry points."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

DEV = Path(__file__).resolve().parents[1]
BACKEND = DEV.parent
SPEC = importlib.util.spec_from_file_location("check_boundaries", DEV / "check_boundaries.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def press_policy():
    policy = json.loads((DEV / "modul-sinirlari.json").read_text())
    policy["path_owners"].update(
        {
            "press_tr.api": "press_tr.kimlik",
            "press_tr.www": "press_tr.kimlik",
        }
    )
    return policy


class PressModuleBoundaryTest(unittest.TestCase):
    def test_entry_points_cannot_write_foreign_doctypes(self):
        scratch = Path(os.environ.get("PANE_SCRATCH_DIR", BACKEND.parent / ".pane/scratch"))
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp)
            foreign = root / "apps/platform_core/platform_core/erisim/doctype/foreign_rule/foreign_rule.json"
            foreign.parent.mkdir(parents=True)
            foreign.write_text(json.dumps({"name": "Foreign Rule", "module": "Erisim"}))

            for entry in ("api", "www"):
                target = root / "apps/press_tr/press_tr" / entry / "example.py"
                target.parent.mkdir(parents=True)
                target.write_text('import frappe\nfrappe.db.set_value("Foreign Rule", "rule", "state", 1)\n')

            errors = CHECKER.check(root, press_policy())
            for entry in ("api", "www"):
                with self.subTest(entry=entry):
                    source = f"apps/press_tr/press_tr/{entry}/example.py:2 WRITE "
                    self.assertTrue(any(error.startswith(source) for error in errors), errors)

    def test_current_press_tree_obeys_module_boundaries(self):
        errors = CHECKER.check(BACKEND, press_policy())
        press_errors = [
            error
            for error in errors
            if error.startswith("apps/press_tr/") or ("CYCLE" in error and "press_tr.kimlik" in error)
        ]
        self.assertEqual(press_errors, [])
