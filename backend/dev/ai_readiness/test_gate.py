"""Exercise the gate through its public command with isolated fake apps."""

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

COMMAND = Path(__file__).resolve().parents[1] / "bin" / "ai-readiness"
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
            [str(COMMAND), "--root", str(self.root), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, int(bool(rules)), result.stderr)
        self.assertTrue(result.stdout, result.stderr)
        violations = json.loads(result.stdout)
        self.assertCountEqual([item["rule"] for item in violations], rules)
        for item in violations:
            self.assertTrue(item["message"])
            self.assertFalse(Path(item["path"]).is_absolute())
            file = self.root / item["path"]
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
        self.write(f"{APP}/tests/test_provider.py", 'MODEL = "gpt-4o-synthetic"\n')
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
            [str(COMMAND), "--root", str(self.root), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn(name, result.stdout.lower())
        self.assertNotIn(spelling, result.stdout)
        findings = json.loads(result.stdout)
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
                self.write(f"{APP}/{module}/tests/test_setup.py", sql)
                path = f"{APP}/{module}/read_card.py"
                self.write(path, sql)
                try:
                    findings = self.scan("sql")
                    self.assertEqual(findings[0]["path"], path)
                finally:
                    (self.root / path).unlink()
                    (self.root / "dev" / policy).unlink()

    def test_missing_naming_checker_reports_not_run(self):
        result = subprocess.run([COMMAND, "--root", self.root, "--json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), [])
        self.assertIn("naming: not_run", result.stderr)

    def test_naming_checker_reports_findings_and_execution_errors(self):
        checker = "dev/naming/check_names.py"
        self.write("apps/example.py", "# Example\n")
        self.write(
            checker,
            """
            import argparse
            import json
            from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
