"""Contract examples from backend/docs/isler/dev-ortam.md and D-11."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

DEV = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_boundaries", DEV / "check_boundaries.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get("PANE_SCRATCH_DIR", DEV.parents[1] / ".pane/scratch"))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {
            "modules": {
                "platform_core.identity": [],
                "platform_core.shell": [],
                "platform_core.ai": ["platform_core.identity", "platform_core.model_gateway"],
                "platform_core.model_gateway": [],
            },
            "public_paths": {
                "platform_core.identity": ["platform_core.identity", "platform_core.identity.api"],
                "platform_core.model_gateway": ["platform_core.model_gateway.api"],
            },
            "path_owners": {"platform_core.api.auth": "platform_core.identity"},
            "forbidden_imports": [
                "openai",
                "anthropic",
                "google.genai",
                "google.generativeai",
                "mistralai",
                "cohere",
                "ollama",
            ],
        }
        self.write(
            "identity/doctype/identity/identity.json", json.dumps({"name": "Identity", "module": "Identity"})
        )

    def write(self, name, text):
        path = self.root / "apps/platform_core/platform_core" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def errors(self):
        return CHECKER.check(self.root, self.policy)

    def test_rejects_import_and_relative_alias(self):
        for code in [
            "import platform_core.identity.api",
            "from ..identity.api import resolve",
            "from platform_core import identity",
            "from .. import identity",
        ]:
            with self.subTest(code=code):
                self.write("shell/api.py", code)
                self.assertTrue(any("IMPORT" in e for e in self.errors()))

    def test_ai_calls_public_function(self):
        self.write("ai/tools.py", "from platform_core.identity.api import resolve")
        self.assertEqual(self.errors(), [])

    def test_ai_calls_public_model_gateway_completion(self):
        self.write("ai/tools.py", "from platform_core.model_gateway.api import complete")
        self.assertEqual(self.errors(), [])
        self.assertTrue(
            (DEV.parent / "apps/platform_core/platform_core/model_gateway/api.py").is_file()
        )

    def test_ai_cannot_import_the_internal_model_gateway(self):
        self.write("ai/tools.py", "from platform_core.model_gateway.gateway import complete")
        self.assertTrue(any("PUBLIC" in error for error in self.errors()))

    def test_ai_cannot_call_private_function_or_internal_module(self):
        for code in [
            "from platform_core.identity.api import _resolve",
            "from platform_core.identity.api import *",
            "import platform_core.identity.internal",
        ]:
            with self.subTest(code=code):
                self.write("ai/tools.py", code)
                self.assertTrue(any("PUBLIC" in e for e in self.errors()))

    def test_gateway_cannot_call_other_modules(self):
        self.write("model_gateway/route.py", "from platform_core.identity.api import resolve")
        self.assertTrue(any("IMPORT" in e for e in self.errors()))

    def test_other_modules_cannot_call_ai_or_gateway(self):
        for target in ["ai", "model_gateway"]:
            with self.subTest(target=target):
                self.write("identity/api.py", f"import platform_core.{target}.api")
                self.assertTrue(any("IMPORT" in e for e in self.errors()))

    def test_cycles_are_reported(self):
        self.policy["modules"]["platform_core.identity"] = ["platform_core.shell"]
        self.policy["modules"]["platform_core.shell"] = ["platform_core.identity"]
        self.policy["public_paths"]["platform_core.shell"] = ["platform_core.shell.api"]
        self.write("identity/api.py", "import platform_core.shell.api")
        self.write("shell/api.py", "import platform_core.identity.api")
        self.assertTrue(any("CYCLE" in e for e in self.errors()))

    def test_provider_imports_are_rejected_everywhere(self):
        for code in [
            "import openai as sdk",
            "from google import genai",
            "from google.generativeai import GenerativeModel",
            "import anthropic",
            "import mistralai",
            "import cohere",
            "import ollama",
        ]:
            with self.subTest(code=code):
                self.write("model_gateway/route.py", code)
                self.assertTrue(any("PROVIDER" in e for e in self.errors()))

    def test_dynamic_literal_imports_are_checked(self):
        self.write(
            "shell/api.py",
            """from importlib import import_module as load
load("platform_core.identity.api")""",
        )
        self.assertTrue(any("IMPORT" in e for e in self.errors()))
        self.write(
            "shell/api.py",
            """import importlib
importlib.import_module("openai")""",
        )
        self.assertTrue(any("PROVIDER" in e for e in self.errors()))

    def test_foreign_writes_are_rejected(self):
        for code in [
            """import frappe
frappe.db.set_value("Identity", "demo", "enabled", 1)""",
            """from frappe import db
db.set_value("Identity", "demo", "enabled", 1)""",
            """import frappe as f
f.delete_doc("Identity", "demo")""",
            """import frappe
frappe.db.delete("Identity", {"name": "demo"})""",
            """import frappe
doc = frappe.get_doc("Identity", "demo")
doc.save()""",
            """import frappe
doc: object = frappe.get_doc("Identity", "demo")
doc.save()""",
            """import frappe
frappe.get_doc({"doctype": "Identity"}).insert()""",
            """import frappe
doc = frappe.new_doc("Identity")
doc.db_set("enabled", 1)""",
            """import frappe
frappe.get_doc(doctype="Identity", name="demo").save()""",
        ]:
            with self.subTest(code=code):
                self.write("shell/api.py", code)
                self.assertTrue(any("WRITE" in e for e in self.errors()))

    def test_owned_writes_and_foreign_reads_are_allowed(self):
        self.write(
            "identity/api.py",
            """import frappe
frappe.db.set_value("Identity", "demo", "enabled", 1)""",
        )
        self.write(
            "shell/api.py",
            """import frappe
doc = frappe.get_doc("Identity", "demo")
print(doc.name)""",
        )
        self.assertEqual(self.errors(), [])

    def test_api_paths_have_module_owner(self):
        self.write("api/auth.py", "import platform_core.shell.api")
        self.assertTrue(any("IMPORT" in e for e in self.errors()))

    def test_invalid_python_fails_closed(self):
        self.write("shell/api.py", "def invalid(")
        self.assertTrue(any("SYNTAX" in e for e in self.errors()))


if __name__ == "__main__":
    unittest.main()
