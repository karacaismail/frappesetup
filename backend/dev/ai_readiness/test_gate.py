"""Exercise the gate through its public command with isolated fake apps."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

COMMAND = Path(__file__).resolve().parents[1] / "bin" / "ai-readiness"
GATE = COMMAND.parents[1] / "ai_readiness" / "gate.py"
SCRATCH = COMMAND.parents[3] / ".pane" / "scratch"
APP = "apps/sample_app/sample_app"
DOCTYPE = f"{APP}/records/doctype/contact_card/contact_card.json"
CONTRACT = "contracts/sample_app.openapi.yaml"


class GateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name)
        subprocess.run(["git", "init", "--quiet", self.repository], check=True)
        self.root = self.repository / "backend"
        self.write(f"{APP}/__init__.py", "")
        self.write(f"{APP}/hooks.py", 'app_name = "sample_app"\n')

    def write(self, path, content):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")

    def scan(self, *rules):
        result = subprocess.run(
            [sys.executable, "-B", str(GATE), "--root", str(self.root), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, int(bool(rules)), result.stderr)
        self.assertTrue(result.stdout, result.stderr)
        violations = json.loads(result.stdout)["findings"]
        self.assertCountEqual([item["rule"] for item in violations], rules, violations)
        for item in violations:
            self.assertTrue(item["message"])
            self.assertFalse(Path(item["path"]).is_absolute())
            file = self.root / item["path"]
            if item["rule"] == "input":
                continue
            self.assertTrue(file.is_file(), item)
            self.assertLessEqual(1, item["line"], item)
            self.assertLessEqual(item["line"], len(file.read_text().splitlines()), item)
        return violations

    def write_doctype(self, description, field_description):
        document = {
            "doctype": "DocType",
            "name": "Contact Card",
            "description": description,
            "fields": [
                {"fieldtype": "Section Break", "fieldname": "section"},
                {"fieldtype": "Column Break", "fieldname": "column"},
                {"fieldtype": "Tab Break", "fieldname": "tab"},
                {"fieldtype": "Data", "fieldname": "label", "description": field_description},
            ],
        }
        self.write(DOCTYPE, json.dumps(document, indent=2))

    def write_contract(self, function="run", summary='"Read a card"', description="Read a card."):
        self.write(
            CONTRACT,
            f"""
            openapi: 3.1.0
            info:
              title: Contact Cards
              version: 1.0.0
            paths:
              /api/method/sample_app.api.{function}:
                post:
                  operationId: readCard
                  summary: {summary}
                  description: |
                    {description}
                  responses:
                    '200':
                      description: OK
            """,
        )

    def test_doctype_and_field_descriptions(self):
        self.write_doctype("A contact card.", "The card label.")
        self.scan()
        self.write_doctype(" ", None)
        violations = self.scan("doctype", "doctype")
        self.assertEqual({item["path"] for item in violations}, {DOCTYPE})
        self.assertEqual(len({item["line"] for item in violations}), 2)

    def test_whitelisted_endpoint_and_contract_match_in_both_directions(self):
        self.write(
            f"{APP}/api.py",
            """
            import frappe

            @frappe.whitelist(methods=["POST"])
            def run():
                return {}
            """,
        )
        self.scan("endpoint")
        self.write_contract()
        self.scan()
        self.write_contract(function="missing")
        self.scan("endpoint", "endpoint")

    def test_contract_operation_needs_summary_and_description(self):
        self.write(
            f"{APP}/api.py",
            """
            import frappe

            @frappe.whitelist()
            def run():
                return {}
            """,
        )
        self.write_contract()
        self.scan()
        for summary, description in [('""', "Read a card."), ('"Read a card"', "")]:
            with self.subTest(summary=summary, description=description):
                self.write_contract(summary=summary, description=description)
                self.scan("endpoint")

    def test_provider_imports(self):
        path = f"{APP}/provider.py"
        self.write(path, "from urllib import request\n# import openai\n")
        self.scan()
        self.write(path, "import openai as sdk\nfrom google import generativeai\n")
        self.scan("provider", "provider")

    def test_model_names_in_code_and_fixtures(self):
        self.write(
            f"{APP}/tests/test_provider.py",
            'from unittest import TestCase\nclass Sample(TestCase):\n    MODEL = "gpt-4o-synthetic"\n',
        )
        self.write(f"{APP}/provider.py", 'PROVIDER_ID = "provider-id"\n')
        self.scan()
        self.write(f"{APP}/provider.py", 'MODEL = "gpt-4o"\n')
        self.scan("model")

    def test_scheduler_registration_in_hooks(self):
        self.write(f"{APP}/jobs.py", "scheduler_events = {}\n")
        self.write(f"{APP}/hooks.py", "# scheduler_events = {}\n")
        self.scan()
        self.write(f"{APP}/hooks.py", "scheduler_events = {}\n")
        self.scan("scheduler")

    def test_forbidden_name_in_tracked_contents_and_paths(self):
        name = "".join(map(chr, (99, 114, 111, 110, 104, 114)))
        spelling = "._- ".join(name.upper())
        tracked = self.repository / "guide.txt"
        tracked.write_text(f"Heading\n{spelling}\n", encoding="utf-8")
        nested = self.repository / name
        nested.mkdir()
        (nested / "readme.txt").write_text("Example", encoding="utf-8")
        (self.repository / "untracked.txt").write_text(name, encoding="utf-8")
        self.scan()
        subprocess.run(["git", "add", "--", tracked, nested], cwd=self.repository, check=True)
        result = subprocess.run(
            [sys.executable, "-B", str(GATE), "--root", str(self.root), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn(name, result.stdout.lower())
        self.assertNotIn(spelling, result.stdout)
        findings = json.loads(result.stdout)["findings"]
        self.assertEqual([finding["rule"] for finding in findings], ["forbidden-name"] * 2)
        self.assertIn(("guide.txt", 2), {(finding["path"], finding["line"]) for finding in findings})

    def test_sql_scope_follows_module_policy_through_rename(self):
        sql = 'import frappe\n\nfrappe.db.sql("SELECT 1")\n'
        for module, policy in (
            ("yapay_zeka", "modul-sinirlari.json"),
            ("ai", "module-boundaries.json"),
        ):
            with self.subTest(module=module):
                self.write(
                    f"dev/{policy}",
                    json.dumps({"path_owners": {"sample_app.api.ai": f"sample_app.{module}"}}),
                )
                self.write(
                    f"{APP}/{module}/tests/test_setup.py",
                    "from unittest import TestCase\nimport frappe\n"
                    "class Setup(TestCase):\n    def test_setup(self):\n"
                    "        frappe.db.sql('SELECT 1')\n",
                )
                path = f"{APP}/{module}/read_card.py"
                self.write(path, sql)
                try:
                    findings = self.scan("sql")
                    self.assertEqual(findings[0]["path"], path)
                finally:
                    (self.root / path).unlink()
                    (self.root / "dev" / policy).unlink()

    def test_duplicate_decision_number_reports_later_note(self):
        self.write("docs/kararlar/0010-one.md", "# One")
        self.write("docs/kararlar/0010-two.md", "# Two")
        self.write("docs/kararlar/00101-three.md", "# Three")
        self.write("docs/kararlar/0011-four.md", "# Four")
        self.write("docs/elsewhere/0010-other.md", "# Elsewhere")
        (finding,) = self.scan("decision-number")
        self.assertEqual(finding["path"], "docs/kararlar/0010-two.md")
        self.assertIn("0010-one.md", finding["message"])

    def test_website_user_methods_require_real_same_app_whitelisted_functions(self):
        self.write(
            f"{APP}/api.py",
            "import frappe\n@frappe.whitelist()\ndef run(): pass\ndef private(): pass",
        )
        self.write_contract()
        allowed = [
            "sample_app.api.run",
            "frappe.auth.get_logged_user",
            "logout",
            "frappe.desk.search.search_link",
        ]
        self.write(f"{APP}/hooks.py", f"website_user_allowed_methods = {allowed!r}")
        self.scan()
        for method in (
            "sample_app.api.missing",
            "sample_app.api.private",
            "frappe.auth.login",
            "other_app.api.run",
        ):
            with self.subTest(method=method):
                self.write(f"{APP}/hooks.py", f"website_user_allowed_methods = [{method!r}]")
                (finding,) = self.scan("website-user")
                self.assertIn(method, finding["message"])

    def test_website_user_accepts_non_manager_role_alternative(self):
        self.write(f"{APP}/hooks.py", 'website_user_allowed_methods = ["sample_app.api.run"]')
        self.write(
            f"{APP}/api.py",
            'import frappe\n@frappe.whitelist()\ndef run(): frappe.only_for(["Customer", "System Manager"])',
        )
        self.write_contract()
        self.scan()

    def test_website_user_rejects_privileged_endpoints(self):
        methods = (
            ("platform_core.api.mobile", "v1_cleanup", "pass"),
            ("platform_core.api.mobile", "revoke_user_installations", "pass"),
            ("press_tr.api.identity", "ensure_team", "pass"),
            ("press_tr.api.identity", "remove_team_member", "pass"),
            ("sample_app.api", "manage", 'frappe.only_for("System Manager")'),
            ("sample_app.api", "manage", 'frappe.only_for(roles="System Manager")'),
        )
        for module, method, body in methods:
            with self.subTest(method=method):
                app = module.split(".")[0]
                package = f"apps/{app}/{app}"
                source_path = f"{package}/{module.partition('.')[2].replace('.', '/')}.py"
                self.write(source_path, f"import frappe\n@frappe.whitelist()\ndef {method}(): {body}")
                self.write(f"{package}/hooks.py", f"website_user_allowed_methods = ['{module}.{method}']")
                self.write_contract(function=method)
                contract = self.root / CONTRACT
                contract.write_text(
                    contract.read_text().replace(f"sample_app.api.{method}", f"{module}.{method}")
                )
                if app == "platform_core":
                    self.write(
                        "dev/module-boundaries.json",
                        '{"path_owners": {"platform_core.api.ai": "platform_core.ai"}}',
                    )
                    self.write(f"{package}/ai/__init__.py", "")
                try:
                    (finding,) = self.scan("website-user")
                    self.assertIn(f"{module}.{method}", finding["message"])
                finally:
                    for path in (contract, self.root / f"{package}/hooks.py", self.root / source_path):
                        path.unlink()

    def test_website_user_rejects_rebound_whitelisted_name(self):
        self.write(f"{APP}/hooks.py", 'website_user_allowed_methods = ["sample_app.api.run"]')
        self.write_contract()
        for rebind in ("run = None", "def run(): pass", "if enabled: run = None"):
            with self.subTest(rebind=rebind):
                self.write(
                    f"{APP}/api.py",
                    "import frappe\n@frappe.whitelist()\ndef run(): pass\n" + rebind,
                )
                rules = ("website-user", "endpoint") if rebind.startswith("def") else ("website-user",)
                findings = self.scan(*rules)
                finding = next(item for item in findings if item["rule"] == "website-user")
                self.assertIn("sample_app.api.run", finding["message"])

    def test_website_user_rejects_rebound_package_export(self):
        self.write(f"{APP}/hooks.py", 'website_user_allowed_methods = ["sample_app.run"]')
        self.write(f"{APP}/api.py", "import frappe\n@frappe.whitelist()\ndef run(): pass")
        self.write_contract()
        self.write(f"{APP}/__init__.py", "from .api import run\nrun = None")
        (finding,) = self.scan("website-user")
        self.assertIn("sample_app.run", finding["message"])

    def test_website_user_rejects_dynamic_hook_construction(self):
        self.write(
            f"{APP}/hooks.py", 'website_user_allowed_methods = []\nwebsite_user_allowed_methods += ["logout"]'
        )
        (finding,) = self.scan("website-user")
        self.assertEqual(finding["line"], 2)

    def test_website_user_rejects_mutable_alias_for_list(self):
        self.write(
            f"{APP}/hooks.py",
            'METHODS = []\nwebsite_user_allowed_methods = METHODS\nMETHODS.append("frappe.auth.login")',
        )
        (finding,) = self.scan("website-user")
        self.assertEqual(finding["line"], 2)

    def test_website_user_rejects_privileged_override_of_core_method(self):
        self.write(
            f"{APP}/hooks.py",
            """
            website_user_allowed_methods = ["frappe.desk.search.search_link"]
            override_whitelisted_methods = {"frappe.desk.search.search_link": "sample_app.api.run"}
            """,
        )
        self.write(
            f"{APP}/api.py",
            'import frappe\n@frappe.whitelist()\ndef run(): frappe.only_for("System Manager")',
        )
        self.write_contract()
        contract = self.root / CONTRACT
        contract.write_text(
            contract.read_text().replace(
                "responses:",
                "x-frappe-original: frappe.desk.search.search_link\n      responses:",
            )
        )
        (finding,) = self.scan("website-user")
        self.assertIn("sample_app.api.run", finding["message"])

    def test_website_user_checks_all_override_candidates(self):
        self.write(
            f"{APP}/hooks.py",
            """
            website_user_allowed_methods = ["frappe.desk.search.search_link"]
            override_whitelisted_methods = {
                "frappe.desk.search.search_link": ["sample_app.api.manage", "sample_app.api.run"],
            }
            """,
        )
        self.write(
            f"{APP}/api.py",
            """
            import frappe

            @frappe.whitelist()
            def manage():
                frappe.only_for("System Manager")

            @frappe.whitelist()
            def run():
                pass
            """,
        )
        self.write(
            CONTRACT,
            json.dumps(
                {
                    "paths": {
                        "/api/method/sample_app.api.manage": {
                            "post": {"summary": "Manage", "description": "Manage."}
                        },
                        "/api/method/sample_app.api.run": {
                            "post": {
                                "summary": "Read",
                                "description": "Read.",
                                "x-frappe-original": "frappe.desk.search.search_link",
                            }
                        },
                    }
                }
            ),
        )
        (finding,) = self.scan("website-user")
        self.assertIn("sample_app.api.manage", finding["message"])

    def write_naming_findings(self, *rules):
        records = [
            {"path": f"backend/{APP}/hooks.py", "line": 1, "rule": rule, "message": f"Review {rule}."}
            for rule in rules
        ]
        self.write(
            "dev/naming/check_names.py",
            f"print({json.dumps(records)!r})\nraise SystemExit({int(bool(records))})",
        )

    def run_gate(self, *args):
        return subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, *args], capture_output=True, text=True
        )

    def test_naming_advisory_preserves_findings_without_failing_gate(self):
        self.write("dev/naming/enforcement.json", '{"mode": "advisory"}')
        self.write_naming_findings("legacy-name", "source-text")
        result = self.run_gate("--json")
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["naming"], "warn")
        self.assertEqual(payload["checks"]["naming_mode"], "advisory")
        self.assertEqual(payload["checks"]["naming_mode_source"], "file")
        self.assertEqual(
            [(finding["rule"], finding["severity"]) for finding in payload["findings"]],
            [("naming.legacy-name", "warning"), ("naming.source-text", "warning")],
        )
        self.write("docs/kararlar/0010-first.md", "# First")
        self.write("docs/kararlar/0010-second.md", "# Second")
        self.assertEqual(self.run_gate("--json").returncode, 1)

    def test_naming_enforce_blocks_only_four_rule_codes(self):
        self.write("dev/naming/enforcement.json", '{"mode": "enforce"}')
        blocking = ("legacy-name", "module-name", "translation-binding", "turkish-name")
        for rule in blocking:
            with self.subTest(rule=rule):
                self.write_naming_findings(rule, "source-text")
                result = self.run_gate("--json")
                self.assertEqual(result.returncode, 1, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["checks"]["naming_mode"], "enforce")
                self.assertEqual(payload["checks"]["naming"], "fail")
                severity = {finding["rule"]: finding["severity"] for finding in payload["findings"]}
                self.assertEqual(severity, {f"naming.{rule}": "error", "naming.source-text": "warning"})
        self.write_naming_findings("source-text")
        self.assertEqual(self.run_gate("--json").returncode, 0)

    def test_naming_defaults_to_advisory_and_reports_missing_policy(self):
        self.write_naming_findings("module-name")
        result = self.run_gate("--json")
        self.assertEqual(result.returncode, 0, result.stdout)
        checks = json.loads(result.stdout)["checks"]
        self.assertEqual(checks["naming_mode"], "advisory")
        self.assertEqual(checks["naming_mode_source"], "default")
        text_result = self.run_gate()
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn("enforcement.json missing", text_result.stderr)
        self.assertIn("Warning: ", text_result.stdout)

    def test_invalid_naming_mode_is_a_configuration_error(self):
        self.write("dev/naming/enforcement.json", '{"mode": "typo"}')
        result = self.run_gate("--json")
        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["naming_mode_source"], "invalid")
        self.assertEqual([finding["rule"] for finding in payload["findings"]], ["naming-config"])

    def test_missing_naming_checker_reports_not_run(self):
        result = subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, "--json"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "findings": [],
                "checks": {
                    "naming": "not_run",
                    "naming_mode": "advisory",
                    "naming_mode_source": "default",
                    "translation_core": "not_run",
                },
            },
        )
        self.assertEqual(result.stderr, "")

    def test_naming_checker_reports_findings_and_execution_errors(self):
        checker = "dev/naming/check_names.py"
        self.write("dev/naming/enforcement.json", '{"mode": "enforce"}')
        self.write("apps/example.py", "# Example\n")
        self.write(
            checker,
            """
            import argparse
            import json
            import sys
            from pathlib import Path

            assert sys.flags.isolated
            parser = argparse.ArgumentParser()
            parser.add_argument("--root", type=Path, required=True)
            parser.add_argument("--json", action="store_true", required=True)
            args = parser.parse_args()
            assert (args.root / "backend/apps/example.py").is_file()
            print(json.dumps([{
                "path": "backend/apps/example.py", "line": 1,
                "rule": "module-name", "message": "Invalid module name."
            }]))
            raise SystemExit(1)
            """,
        )
        findings = self.scan("naming.module-name")
        self.assertEqual(findings[0]["path"], "apps/example.py")
        self.write(checker, "raise SystemExit(2)")
        self.scan("naming")

    def test_whitelisted_test_endpoint_is_reported_even_with_contract(self):
        cases = (
            ("identity/tests/mobile_stub.py", "identity.tests.mobile_stub"),
            ("test_mobile.py", "test_mobile"),
            ("test_support/__init__.py", "test_support"),
        )
        for relative, module in cases:
            with self.subTest(relative=relative):
                path = f"{APP}/{relative}"
                self.write(
                    path,
                    """
                    from frappe import whitelist as expose

                    @expose()
                    def whoami():
                        return {}
                    """,
                )
                self.write(
                    CONTRACT,
                    f"""
                    paths:
                      /api/method/sample_app.{module}.whoami:
                        post:
                          summary: Read identity
                          description: Read the request identity.
                    """,
                )
                try:
                    findings = self.scan("test-endpoint")
                    self.assertEqual((findings[0]["path"], findings[0]["line"]), (path, 4))
                finally:
                    (self.root / path).unlink()

    def test_whitelisted_wrapper_assigned_at_import_is_reported(self):
        self.write(
            f"{APP}/identity/tests/mobile_stub.py",
            """
            import frappe

            def whoami():
                return {}

            whoami = frappe.whitelist()(whoami)
            """,
        )
        findings = self.scan("endpoint", "test-endpoint")
        self.assertEqual({finding["line"] for finding in findings}, {6})

    def test_test_only_registration_does_not_expose_an_endpoint_on_import(self):
        self.write(
            f"{APP}/identity/tests/mobile_stub.py",
            """
            import frappe

            def whoami():
                return {}

            def register():
                if not frappe.in_test:
                    raise RuntimeError("Only available in tests.")
                return frappe.whitelist()(whoami)
            """,
        )
        self.scan()

    def test_sql_in_ai_module_and_registered_tool(self):
        command = 'import frappe\n\ndef run():\n    return frappe.db.sql("SELECT 1")\n'
        self.write(f"{APP}/tools.py", command)
        self.write(
            f"{APP}/declarations.py",
            """
            def tools():
                return [{
                    "name": "read_card",
                    "description": "Read a card.",
                    "arguments": "sample_app.arguments.ReadCard",
                    "kind": "read",
                    "handler": "sample_app.tools.run",
                }]
            """,
        )
        self.scan()
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.declarations.tools"]\n')
        self.scan("sql")

    def test_computed_tool_declarations(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        self.write(
            f"{APP}/tools.py",
            """
            import frappe
            PATH = "sample_app.tools."
            BASE = {"handler": PATH + "run"}

            def declare():
                return [{**BASE, "prepare": f"{PATH}prepare"}]

            def run():
                frappe.db.sql("SELECT 1")

            def prepare():
                frappe.db.sql("SELECT 1")
            """,
        )
        self.scan("sql", "sql")

    def test_unresolved_and_empty_tool_declarations(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        for result in ('[{"handler": build_path()}]', '[{"name": "read"}]', "[]"):
            with self.subTest(result=result):
                self.write(f"{APP}/tools.py", f"def declare():\n    return {result}\n")
                self.scan("sql")

    def test_nested_whitelist_and_external_overrides(self):
        self.write(
            f"{APP}/api.py",
            """
            import frappe
            def factory():
                @frappe.whitelist(allow_guest=True)
                def wrapper():
                    pass
                return wrapper
            run = factory()
            """,
        )
        self.scan("endpoint")
        self.write(
            f"{APP}/hooks.py", 'override_whitelisted_methods = {"frappe.example.run": "sample_app.api.run"}'
        )
        self.scan("endpoint", "endpoint")
        self.write_contract()
        contract = self.root / CONTRACT
        contract.write_text(
            contract.read_text().replace(
                "responses:", "x-frappe-original: frappe.example.run\n      responses:"
            )
        )
        self.scan()

    def test_imported_test_base_exempts_shared_subclasses(self):
        self.write(
            "dev/module-boundaries.json", json.dumps({"path_owners": {"sample_app.api.ai": "sample_app.ai"}})
        )
        self.write(
            f"{APP}/ai/tests/base.py",
            """
            from frappe.tests import IntegrationTestCase
            class CommonCase(IntegrationTestCase):
                pass
        """,
        )
        self.write(
            f"{APP}/ai/tests/test_x.py",
            """
            import frappe
            from .base import CommonCase as Base
            class Check(Base):
                def test_sql(self):
                    frappe.db.sql("SELECT 1")
                    model = "gpt-4o"
        """,
        )
        self.scan()

    def test_frappe_test_base_exports_exempt_test_class(self):
        for module, base in (
            ("frappe.tests.test_api", "FrappeAPITestCase"),
            ("frappe.tests.classes", "IntegrationTestCase"),
            ("frappe.tests.classes", "UnitTestCase"),
        ):
            with self.subTest(module=module, base=base):
                self.write(
                    f"{APP}/tests/test_api.py",
                    f"from {module} import {base} as Base\n"
                    "class Check(Base):\n    def test_model(self):\n"
                    "        model = 'gpt-4o'\n",
                )
                self.scan()

    def test_local_import_does_not_turn_non_test_base_into_test_case(self):
        self.write(
            "dev/module-boundaries.json", json.dumps({"path_owners": {"sample_app.api.ai": "sample_app.ai"}})
        )
        self.write(
            f"{APP}/ai/tests/base.py",
            """
            class Base:
                pass
            def local_test():
                from unittest import TestCase as Base
            class CommonCase(Base):
                pass
        """,
        )
        self.write(
            f"{APP}/ai/tests/test_x.py",
            """
            import frappe
            from .base import CommonCase
            class Check(CommonCase):
                def run(self):
                    frappe.db.sql("SELECT 1")
        """,
        )
        self.scan("sql")

    def test_override_requires_original_on_target_operation(self):
        self.write(f"{APP}/api.py", "import frappe\n@frappe.whitelist()\ndef run(): pass\n")
        self.write(
            f"{APP}/hooks.py",
            """
            override_whitelisted_methods = {
                "frappe.example.run": "sample_app.api.run",
                "hrms.example.run": "sample_app.api.run",
            }
        """,
        )
        self.write_contract()
        self.scan("endpoint", "endpoint")
        path = self.root / CONTRACT
        source = path.read_text()
        path.write_text(
            source
            + """
  /api/method/frappe.example.run:
    post:
      summary: Run the original route.
      description: Run a card.
"""
        )
        self.scan("endpoint", "endpoint")
        for extension in (
            'x-frappe-original: ["frappe.example.run", hrms.example.run]',
            "x-frappe-original:\n      - frappe.example.run\n      - hrms.example.run",
        ):
            with self.subTest(extension=extension):
                path.write_text(source.replace("responses:", extension + "\n      responses:"))
                self.scan()
        path.write_text(
            json.dumps(
                {
                    "paths": {
                        "/api/method/sample_app.api.run": {
                            "post": {
                                "summary": "Run.",
                                "description": "Run.",
                                "x-frappe-original": ["frappe.example.run", "hrms.example.run"],
                            }
                        }
                    }
                }
            )
        )
        self.scan()

    def test_registered_tool_follows_same_app_helper_and_breaks_cycles(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        self.write(
            f"{APP}/tools.py",
            """
            from . import service as helpers
            def declare():
                return [{"handler": "sample_app.tools.run"}]
            def run():
                helpers.read()
        """,
        )
        self.write(
            f"{APP}/service.py",
            """
            import frappe
            from .tools import run
            def read():
                run()
                frappe.db.sql("SELECT 1")
        """,
        )
        self.scan("sql")

    def test_tool_sql_follows_nested_calls_and_function_references(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        self.write(
            f"{APP}/queries.py",
            "import frappe\ndef read(): frappe.db.sql('SELECT 1')",
        )
        for body in (
            "    def inner():\n        from .queries import read\n        read()\n    inner()",
            "    from .queries import read\n    apply(read)",
        ):
            with self.subTest(body=body):
                self.write(
                    f"{APP}/tools.py",
                    'def declare(): return [{"handler": "sample_app.tools.run"}]\ndef run():\n' + body,
                )
                (finding,) = self.scan("sql")
                self.assertEqual(finding["path"], f"{APP}/queries.py")

    def test_tool_sql_ignores_uncalled_and_other_app_functions(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.declarations.declare"]')
        self.write(
            f"{APP}/declarations.py",
            'def declare(): return [{"handler": "sample_app.tools.run"}]',
        )
        self.write(
            f"{APP}/tools.py",
            """
            import frappe
            from other_app.service import external
            def run():
                safe()
                external()
            def safe():
                pass
            def unused():
                frappe.db.sql("SELECT 1")
            """,
        )
        self.write(
            "apps/other_app/other_app/service.py",
            """
            import frappe
            def external():
                frappe.db.sql("SELECT 1")
            """,
        )
        self.scan()

    def test_registered_tool_follows_package_reexport(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.declare"]')
        self.write(f"{APP}/__init__.py", "from .tools import declare")
        self.write(
            f"{APP}/tools.py",
            """
            import frappe
            def declare():
                return [{"handler": "sample_app.tools.run"}]
            def run():
                frappe.db.sql("SELECT 1")
            """,
        )
        (finding,) = self.scan("sql")
        self.assertEqual(finding["path"], f"{APP}/tools.py")

    def test_tool_helper_follows_chained_package_reexports(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.declarations.declare"]')
        self.write(
            f"{APP}/declarations.py",
            'def declare(): return [{"handler": "sample_app.tools.run"}]',
        )
        self.write(f"{APP}/__init__.py", "from .helpers import read")
        self.write(f"{APP}/helpers/__init__.py", "from .queries import query as read")
        self.write(f"{APP}/tools.py", "from . import read\ndef run(): read()")
        self.write(
            f"{APP}/helpers/queries.py",
            """
            import frappe
            def query():
                frappe.db.sql("SELECT 1")
            """,
        )
        (finding,) = self.scan("sql")
        self.assertEqual(finding["path"], f"{APP}/helpers/queries.py")

    def test_tool_helper_resolution_ignores_unrelated_local_alias(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        self.write(
            f"{APP}/tools.py",
            """
            from .service import raw as read
            def declare():
                return [{"handler": "sample_app.tools.run"}]
            def run():
                read()
            def unrelated():
                from .service import safe as read
                read()
        """,
        )
        self.write(
            f"{APP}/service.py",
            """
            import frappe
            def raw():
                frappe.db.sql("SELECT 1")
            def safe():
                pass
        """,
        )
        self.scan("sql")

    def test_sql_method_references(self):
        self.write(
            "dev/module-boundaries.json", json.dumps({"path_owners": {"sample_app.api.ai": "sample_app.ai"}})
        )
        self.write(
            f"{APP}/ai.py",
            """
            import frappe
            run = frappe.db.sql
            map(frappe.db.sql, queries)
        """,
        )
        self.scan("sql", "sql")

    def test_runtime_whitelist_in_production(self):
        self.write(f"{APP}/hooks.py", 'before_request = ["sample_app.api.register"]')
        self.write(
            f"{APP}/api.py",
            """
            import frappe
            def read():
                pass
            def register():
                frappe.whitelist(allow_guest=True)(read)
        """,
        )
        self.scan("endpoint")

    def test_frappe_provider_imports(self):
        self.write(
            f"{APP}/api.py",
            """
            import frappe
            frappe.get_attr("transformers.pipeline")
            frappe.get_module("vertexai")
            frappe.get_module("genai")
        """,
        )
        self.scan("provider", "provider", "provider")

    def test_scheduled_record_fixtures(self):
        self.write(
            f"{APP}/fixtures/schedules.json",
            json.dumps([{"doctype": "Auto Repeat"}, {"doctype": "Auto Email Report"}]),
        )
        self.scan("scheduler", "scheduler")

    def test_sql_public_paths_and_database_aliases(self):
        self.write(
            "dev/module-boundaries.json", json.dumps({"path_owners": {"sample_app.api.ai": "sample_app.ai"}})
        )
        self.write(f"{APP}/ai/__init__.py", "")
        self.write(
            f"{APP}/api/ai.py",
            """
            import frappe
            db = frappe.db
            frappe.local.db.sql("SELECT 1")
            db.sql_list("SELECT 1")
            db.multisql({})
            frappe.db.sql_ddl("SELECT 1")
            getattr(frappe.db, "sql")("SELECT 1")
            """,
        )
        self.scan(*(["sql"] * 5))

    def test_boundary_owner_requires_python_source(self):
        self.write(
            "dev/module-boundaries.json",
            json.dumps({"path_owners": {"sample_app.api.ai": "sample_app.absent"}}),
        )
        self.scan("input")

    def test_production_references_disable_test_exemption(self):
        self.write(
            "dev/module-boundaries.json", json.dumps({"path_owners": {"sample_app.api.ai": "sample_app.ai"}})
        )
        self.write(
            f"{APP}/ai/tests/test_helper.py",
            """
            from unittest import TestCase
            import frappe
            class Helper(TestCase):
                def test_run(self):
                    frappe.db.sql("SELECT 1")
            """,
        )
        self.scan()
        self.write(f"{APP}/ai/service.py", "from .tests.test_helper import Helper")
        self.scan("sql")
        (self.root / f"{APP}/ai/service.py").unlink()
        self.write(f"{APP}/hooks.py", 'after_install = "sample_app.ai.tests.test_helper.Helper.test_run"')
        self.scan("sql")

    def test_provider_families_and_dynamic_imports(self):
        self.write(
            "dev/module-boundaries.json",
            json.dumps({"path_owners": {}, "forbidden_imports": ["example_provider"]}),
        )
        self.write(
            f"{APP}/api.py",
            """
            from langchain_openai import Chat
            from llama_index.core import Index
            import example_provider_plugin
            from importlib import import_module as load
            load("openai")
            load(name="anthropic")
            """,
        )
        self.scan(*(["provider"] * 5))

    def test_model_names_in_assets_and_comments(self):
        self.write(f"{APP}/fixtures/examples.json", '{"model": "llama3.1:8b"}')
        self.write(f"{APP}/public/examples.js", 'export const model = "qwen2.5:7b";')
        self.write(f"{APP}/api.py", "# mistral-large-latest gemini-flash-latest command-r-plus")
        self.scan("model", "model", "model")

    def test_model_scan_checks_decoded_python_strings(self):
        self.write(f"{APP}/api.py", 'ESCAPED = "\\x67pt-4o"\nJOINED = "gpt" "-4o"')
        self.scan("model", "model")

    def test_tool_declaration_rejects_unknown_mapping_key(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        self.write(
            f"{APP}/tools.py",
            """
            def declare():
                return [{"handler": "sample_app.tools.run", role(): "sample_app.tools.prepare"}]
            def run():
                pass
            def prepare():
                pass
            """,
        )
        self.scan("sql")

    def test_tool_declaration_rejects_conditional_path(self):
        self.write(f"{APP}/hooks.py", 'ai_tools = ["sample_app.tools.declare"]')
        self.write(
            f"{APP}/tools.py",
            """
            def declare():
                PATH = "sample_app.tools.first"
                if enabled():
                    PATH = "sample_app.tools.second"
                return [{"handler": PATH}]
            def first():
                pass
            def second():
                pass
            """,
        )
        self.scan("sql")

    def test_model_scan_preserves_numeric_suffix_names(self):
        self.write(f"{APP}/api.py", 'MODEL = "gpt-oss-20b"\nOTHER = "deepseek-r1"')
        self.scan("model", "model")

    def test_nested_whitelist_does_not_prove_unrelated_factory_result(self):
        self.write(
            f"{APP}/api.py",
            """
            import frappe
            def factory():
                @frappe.whitelist(allow_guest=True)
                def wrapper():
                    pass
                return object()
            run = factory()
            """,
        )
        self.write_contract()
        findings = self.scan("endpoint", "endpoint")
        self.assertTrue(any("Cannot resolve nested" in finding["message"] for finding in findings))

    def test_model_scan_accepts_review_item_label(self):
        self.write(f"{APP}/api.py", "# See O3 in the security review.")
        self.scan()
        self.write(f"{APP}/api.py", 'MODEL = "o3"')
        self.scan("model")

    def test_path_code_locates_tracked_entry_without_printing_name(self):
        name = "".join(map(chr, (99, 114, 111, 110, 104, 114)))
        path = self.repository / (name + ".txt")
        path.write_text("Sample")
        subprocess.run(["git", "add", "--", path], cwd=self.repository, check=True)
        from forbidden_name import redact_path

        code = redact_path(path.name).split()[-1].removesuffix("]")
        result = subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, "--path-code", code],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"index": 1, "repository": "."})
        self.assertNotIn(name, result.stdout)

    def test_unicode_and_commit_messages(self):
        from forbidden_name import match_lines

        spelling = "".join(map(chr, (99, 114, 111, 110, 104, 114)))
        for variation in (
            "".join(chr(ord(char) + 0xFEE0) for char in spelling),
            spelling.replace("c", "ć"),
            spelling.replace("c", chr(0x441)),
            spelling.replace("o", chr(0x3BF)),
        ):
            with self.subTest(variation=variation):
                self.assertEqual(list(match_lines([variation])), [1])
        from unittest.mock import patch

        from forbidden_name import commit_findings

        with patch(
            "forbidden_name.git_output",
            side_effect=[b"revision", b"a" * 40 + b"\0" + spelling.encode() + b"\0"],
        ):
            self.assertEqual(
                list(commit_findings(self.repository, None)),
                [("git:aaaaaaaaaaaa", 1, "Forbidden product name in a commit message.")],
            )
        result = subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, "--json"],
            capture_output=True,
            text=True,
            env=dict(os.environ, GIT_DIR=str(self.repository / "absent")),
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_tracks_initialized_submodule_content(self):
        from unittest.mock import patch

        from forbidden_name import tracked_files

        name = "".join(map(chr, (99, 114, 111, 110, 104, 114)))
        child = self.repository / "sample-addon"
        child.mkdir()
        (child / ".git").write_text("gitdir: ../.git/modules/sample-addon")
        (child / "guide.txt").write_text(name)
        with patch(
            "forbidden_name.stage_entries", side_effect=[[("sample-addon", True)], [("guide.txt", False)]]
        ):
            self.assertEqual(
                list(tracked_files(self.repository)),
                [("sample-addon/guide.txt", 1, "Forbidden product name in tracked content.")],
            )

    def test_symlinks_excluded_directories_and_nul(self):
        self.write(f"{APP}/.hidden/broken.py", "!")
        self.write(f"{APP}/node_modules/broken.py", "!")
        self.scan()
        (self.root / f"{APP}/linked.py").symlink_to("missing.py")
        self.write(f"{APP}/broken.py", chr(0))
        self.scan("input", "input")

    def test_supported_python_version(self):
        from unittest.mock import patch

        from gate import supports_python

        with patch("sys.version_info", (3, 13)):
            self.assertFalse(supports_python())
        with patch("sys.version_info", (3, 14)):
            self.assertTrue(supports_python())

    def test_readiness_command_exposes_self_test(self):
        self.assertIn("--self-test", COMMAND.read_text())
        self.assertIn("unittest discover", COMMAND.read_text())

    def test_only_documented_layout_fields_are_exempt(self):
        self.write(
            DOCTYPE,
            json.dumps(
                {
                    "doctype": "DocType",
                    "description": "A record.",
                    "fields": [{"fieldtype": "HTML", "fieldname": "banner"}],
                }
            ),
        )
        self.scan("doctype")

    def test_yaml_accepts_indentless_sequence(self):
        self.write_contract()
        path = self.root / CONTRACT
        path.write_text("tags:\n- name: Cards\n" + path.read_text())
        self.write(f"{APP}/api.py", "import frappe\n@frappe.whitelist()\ndef run(): pass\n")
        self.scan()

    def test_imported_scheduler_and_server_script_fixture(self):
        self.write(f"{APP}/hooks.py", "from .jobs import scheduler_events")
        self.write(
            f"{APP}/fixtures/server_script.json",
            json.dumps([{"doctype": "Server Script", "script_type": "Scheduler Event"}]),
        )
        self.scan("scheduler", "scheduler")


if __name__ == "__main__":
    unittest.main()
