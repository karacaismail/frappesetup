"""Check the preview fixture contract without importing Frappe or access-rule tests."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class AccessFixtureTest(unittest.TestCase):
    def test_creates_two_records_and_one_reader_rule(self):
        created = []
        fake = ModuleType("frappe")

        def get_doc(**values):
            created.append(values)
            return SimpleNamespace(insert=lambda: SimpleNamespace(name=f"fixture-{len(created)}"))

        fake.get_doc = get_doc
        path = Path(__file__).resolve().parents[1] / "preview" / "site-seed.py"
        spec = importlib.util.spec_from_file_location("site_seed", path)
        seed = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": fake}):
            spec.loader.exec_module(seed)
            result = seed.seed_access_fixture()

        doctype = result["E2E_DOCTYPE"]
        reader = result["E2E_PREVIEW_READER_EMAIL"]
        password = result["E2E_PREVIEW_READER_PASSWORD"]
        role, definition, account, rule, visible, hidden = created
        self.assertEqual(account["new_password"], password)
        self.assertGreaterEqual(len(password), 24)
        self.assertEqual(account["roles"], [{"role": role["role_name"]}])
        self.assertEqual(definition["name"], doctype)
        self.assertIn({"role": role["role_name"], "read": 1}, definition["permissions"])
        field = next(field for field in definition["fields"] if field["fieldname"] == rule["match_field"])
        self.assertEqual((field["fieldtype"], field["options"]), ("Link", "User"))
        self.assertEqual((rule["document_type"], rule["scope"], rule["allow_read"]), (doctype, "own", 1))
        self.assertEqual((visible["doctype"], visible[rule["match_field"]]), (doctype, reader))
        self.assertEqual((hidden["doctype"], hidden[rule["match_field"]]), (doctype, "Administrator"))
        self.assertEqual(result["E2E_VISIBLE_RECORD"], "fixture-5")
        self.assertEqual(result["E2E_HIDDEN_RECORD"], "fixture-6")


if __name__ == "__main__":
    unittest.main()
