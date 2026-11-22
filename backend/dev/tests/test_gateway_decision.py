"""Check the model gateway's D-10 decision records against its source."""

import ast
import json
import re
import unittest
from importlib.util import find_spec
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "apps/platform_core"
MODULE = APP / "platform_core/model_gecidi"
DECISION = BACKEND / "docs/kararlar/0004-model-gecidi.md"
PERMISSION_APPROVAL = "Orkestratör, D-10, 22 Kasım 2026 Pazar"


def section(document, title):
    marker = f"## {title}\n"
    return document.split(marker, 1)[1].split("\n## ", 1)[0] if marker in document else ""


class GatewayDecisionTests(unittest.TestCase):
    def setUp(self):
        self.decision = DECISION.read_text(encoding="utf-8")

    def test_decision_compares_ready_options_and_records_selection(self):
        comparison = section(self.decision, "Hazır çözüm karşılaştırması")
        for evidence in ("Frappe", "ERPNext", "LiteLLM", "Ollama", "Lisans", "Seçim nedeni", "https://"):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, comparison)

    def test_approved_first_permissions_match_doctype_definitions(self):
        permissions = section(self.decision, "İlk kayıt izinleri")
        self.assertIn(PERMISSION_APPROVAL, permissions.splitlines())
        documented = set()
        for name, level, roles, actions in re.findall(
            r"\| `([^`]+)` \| (\d) \| ([^|]+) \| ([^|]+) \|", permissions
        ):
            for role in roles.split(", "):
                documented.add((name, int(level), role, tuple(sorted(actions.strip().split(", ")))))
        actual = set()
        for path in (MODULE / "doctype").glob("*/*.json"):
            doctype = json.loads(path.read_text(encoding="utf-8"))
            for entry in doctype["permissions"]:
                actions = tuple(
                    sorted(key for key, value in entry.items() if key not in {"role", "permlevel"} and value)
                )
                actual.add((doctype["name"], entry.get("permlevel", 0), entry["role"], actions))
            if doctype.get("istable") and not doctype["permissions"]:
                actual.add((doctype["name"], 0, "Yok", ("Yok",)))
        self.assertSetEqual(documented, actual)

    def test_module_interface_lists_the_public_methods_and_events(self):
        interface = section(self.decision, "Modül arayüzü")
        self.assertIn("`platform_core.model_gecidi.api.complete`", interface)
        http_module = ast.parse((APP / "platform_core/api/model.py").read_text(encoding="utf-8"))
        for node in http_module.body:
            if isinstance(node, ast.FunctionDef) and any(
                isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "frappe.whitelist"
                for decorator in node.decorator_list
            ):
                self.assertIn(f"`platform_core.api.model.{node.name}`", interface)
        tools_row = next(line for line in interface.splitlines() if "| `ai_tools` |" in line)
        self.assertEqual(
            set(re.findall(r"`([a-z_]+)`", tools_row)),
            {
                "ai_tools",
                "create_ai_api",
                "update_ai_api",
                "create_ai_account",
                "update_ai_account",
                "reconcile_stale_pending",
            },
        )
        for item in (
            "create_ai_api",
            "update_ai_api",
            "create_ai_account",
            "update_ai_account",
            "ai_tools",
            "ai_write_closed_doctypes",
            "validate",
            "on_doctype_update",
            "platform_core.model_gecidi.maintenance.reconcile_stale_pending",
        ):
            with self.subTest(item=item):
                self.assertIn(f"`{item}`", interface)

    @unittest.skipUnless(find_spec("tomllib"), "Manifest checks use Python 3.11 or newer.")
    def test_direct_gateway_dependencies_are_declared_for_bench(self):
        import tomllib

        manifest = tomllib.loads((APP / "pyproject.toml").read_text(encoding="utf-8"))
        runtime = {
            re.split(r"[\s<>=!~@;\[]", requirement, maxsplit=1)[0].lower(): requirement
            for requirement in manifest["project"]["dependencies"]
        }
        self.assertLessEqual({"pydantic", "pypika", "redis", "requests", "urllib3"}, runtime.keys())
        self.assertIn("github.com/frappe/pypika@", runtime["pypika"])
        testing = manifest["tool"]["bench"]["dev-dependencies"]
        self.assertLessEqual({"jsonschema", "PyYAML", "referencing", "Werkzeug"}, testing.keys())
        self.assertEqual(testing["Werkzeug"], "~=3.1.9")
