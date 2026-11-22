"""Exercise application dependency checks through the readiness command."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).with_name("gate.py").resolve()
SCRATCH = GATE.parents[3] / ".pane" / "scratch"
FRAPPE_VERSION = "16.56.0"


class DependencyChecksTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name)
        subprocess.run(["git", "init", "--quiet", self.repository], check=True)
        self.root = self.repository / "backend"

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def manifest(self, directory, name, requirements, optional=()):
        content = f'[project]\nname = "{name}"\ndependencies = {json.dumps(requirements)}\n'
        if optional:
            content += f"[project.optional-dependencies]\nextra = {json.dumps(optional)}\n"
        self.write(f"{directory}/pyproject.toml", content)

    def frappe(self, version=FRAPPE_VERSION, directory="apps/frappe"):
        self.manifest(directory, "frappe", ["Werkzeug==3.1.9", "Other>=2,<3"])
        self.write(f"{directory}/frappe/__init__.py", f'__version__ = "{version}"\n')

    def scan(self, *args, structured=True, frappe_source="", no_site=False):
        return subprocess.run(
            [
                sys.executable,
                *(["-S"] if no_site else []),
                "-B",
                GATE,
                "--root",
                self.root,
                *(["--json"] if structured else []),
                *args,
            ],
            capture_output=True,
            text=True,
            env=dict(os.environ, FRAPPE_SOURCE=frappe_source),
        )

    def test_accepts_app_rules_that_include_frappe_pin(self):
        self.frappe()
        for rule in ("Werkzeug~=3.1.9", "Werkzeug>=3.1,<4", "Werkzeug==3.1.*", "Werkzeug>3.1.8,<=3.1.9"):
            with self.subTest(rule=rule):
                self.manifest("apps/sample_app", "sample_app", [rule])
                result = self.scan()
                self.assertEqual(result.returncode, 0, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["findings"], [])
                self.assertEqual(payload["checks"]["dependency_core"], "pass")

    def test_rejects_rules_excluding_exact_frappe_pin(self):
        self.frappe()
        for rule in ("Werkzeug>=4", "Werkzeug!=3.1.9"):
            with self.subTest(rule=rule):
                self.manifest("apps/sample_app", "sample_app", [rule])
                result = self.scan()
                self.assertEqual(result.returncode, 1, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["checks"]["dependency_core"], "fail")
                (finding,) = payload["findings"]
                self.assertEqual(finding["rule"], "dependency-frappe")
                self.assertEqual(finding["path"], "apps/sample_app/pyproject.toml")
                self.assertIn("3.1.9", finding["message"])
                self.assertNotIn("example.test", finding["message"])

    def test_app_rule_comparison_normalizes_names_and_specifier_order(self):
        self.manifest("apps/first", "first", ["Sample_Name>=2,<3"])
        self.manifest("apps/second", "second", ["sample-name <3,>=2"])
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"]["dependency_apps"], "pass")

        self.manifest("apps/second", "second", [], optional=["sample-name>=4"])
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["dependency_core"], "not_run")
        self.assertEqual(payload["checks"]["dependency_apps"], "fail")
        (finding,) = payload["findings"]
        self.assertEqual(finding["rule"], "dependency-rule")
        self.assertEqual(finding["path"], "apps/second/pyproject.toml")
        self.assertIn("apps/first/pyproject.toml", finding["message"])

    def test_missing_or_different_core_version_does_not_claim_check_ran(self):
        self.manifest("apps/sample_app", "sample_app", ["Werkzeug>=4"])
        for version in (None, "16.55.0"):
            with self.subTest(version=version):
                if version:
                    self.frappe(version)
                result = self.scan()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"]["dependency_core"], "not_run")
                self.assertIn("dependency_core: not_run", self.scan(structured=False).stderr)

    def test_frappe_source_enables_both_checks_and_cli_path_takes_precedence(self):
        self.frappe(directory="external")
        self.write("external/frappe/locale/tr.po", 'msgid "Open"\nmsgstr "Aç"\n')
        self.manifest("apps/sample_app", "sample_app", ["Werkzeug~=3.1.9"])
        self.write("apps/sample_app/sample_app/translations/tr.csv", "Open,Aç,button\n")
        source = self.root / "external"

        result = self.scan(frappe_source=str(source))
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["dependency_core"], "pass")
        self.assertEqual(payload["checks"]["translation_core"], "pass")

        missing = self.root / "missing"
        result = self.scan("--frappe-root", str(missing), frappe_source=str(source))
        checks = json.loads(result.stdout)["checks"]
        self.assertEqual(checks["dependency_core"], "not_run")
        self.assertEqual(checks["translation_core"], "not_run")

        result = self.scan(frappe_source=str(missing))
        self.assertEqual(result.returncode, 0, result.stdout)
        checks = json.loads(result.stdout)["checks"]
        self.assertEqual(checks["dependency_core"], "not_run")
        self.assertEqual(checks["translation_core"], "not_run")

    def test_pip_free_python_and_unsupported_requirements(self):
        self.frappe()
        self.manifest("apps/sample_app", "sample_app", ["Werkzeug~=3.1.9"])
        result = self.scan(no_site=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"]["dependency_core"], "pass")
        self.manifest("apps/sample_app", "sample_app", ["Werkzeug @ git+https://example.test/package"])
        result = self.scan(no_site=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["checks"]["dependency_core"], "not_run")
        self.assertEqual(payload["checks"]["dependency_apps"], "not_run")

    def test_markers_are_skipped_in_both_manifests(self):
        self.frappe()
        for core, app in (
            ("Werkzeug==3.1.9; sys_platform == 'win32'", "Werkzeug>=4"),
            ("Werkzeug==3.1.9", "Werkzeug>=4; sys_platform == 'win32'"),
        ):
            with self.subTest(core=core, app=app):
                self.manifest("apps/frappe", "frappe", [core])
                self.manifest("apps/sample_app", "sample_app", [app])
                result = self.scan()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"]["dependency_core"], "not_run")

    def test_external_frappe_checkout_under_apps_is_excluded(self):
        self.frappe(directory="apps/frappe-16")
        self.write("apps/frappe-16/frappe/api.py", "import frappe\n@frappe.whitelist()\ndef core(): pass")
        self.manifest("apps/sample_app", "sample_app", ["Werkzeug~=3.1.9"])
        for path in ("apps/frappe-16", "apps/frappe-16/frappe"):
            with self.subTest(path=path):
                result = self.scan("--frappe-root", str(self.root / path))
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"]["dependency_core"], "pass")
