"""Test the AV-72 interface against small Frappe app snapshots."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

if sys.version_info < (3, 14):
    raise unittest.SkipTest("Naming tests require Python 3.14 or newer. Run them with python3.14.")

CHECK = Path(__file__).resolve().parents[1] / "check_names.py"


class NamingGateTests(unittest.TestCase):
    def setUp(self):
        scratch = CHECK.parents[3] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        workspace = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        self.app = self.root / "backend/apps/platform_core"
        self.package = self.app / "platform_core"
        self.write(self.package / "modules.txt", "Platform Core\n")
        self.write(
            self.app / "docs/glossary.yaml",
            "- term_tr: Örnek\n  doctype: PLT Example\n  avoid: [invoice_data]\n",
        )

    def write(self, path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def record(self, path, **document):
        self.write(self.package / path, json.dumps(document))

    def run_gate(self, *arguments):
        status, findings = self.gate_findings(*arguments)
        return status, {finding["rule"] for finding in findings}

    def gate_findings(self, *arguments):
        subprocess.run(["git", "-C", str(self.root), "add", "backend"], check=True)
        result = subprocess.run(
            [sys.executable, str(CHECK), "--root", str(self.root), "--json", *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_source_text_reports_turkish_source_with_line_and_example(self):
        self.write(
            self.package / "doctype/example/example.json",
            '{\n  "doctype": "DocType",\n  "title": "Baslik",\n  "fields": [\n'
            '    {"label": "Kayıt", "description": "Alan aciklamasi", "fieldtype": "Select", '
            '"options": "Open\\nKapali"},\n'
            '    {"fieldtype": "Link", "options": "Kullanici"}\n  ]\n}\n',
        )
        self.write(
            self.package / "view.py",
            'import frappe\nfrappe._("Giris yapin")\nfrappe.throw(frappe._("Kayıt yok"))\n'
            'frappe.msgprint(msg="İşlem tamamlandı")\nfrappe.throw("Record is missing.")\n',
        )
        self.write(
            self.package / "view.js",
            "// __('Giriş')\nconst caption = __('Giris yapin');\n",
        )
        self.write(
            self.root / "backend/contracts/example.openapi.yaml",
            "openapi: 3.1.0\ninfo:\n  summary: Kayit getir\n  description: >-\n"
            "    Alan bilgisi dönülür.\n  title: Giriş\n",
        )
        for relative in ("tests/test_view.py", "fixtures/view.js", "translations/view.js", "README.md"):
            self.write(self.package / relative, 'frappe._("Kayıt yok")\n')
        status, findings = self.gate_findings("--source-text")
        self.assertEqual(status, 1)
        self.assertEqual({finding["rule"] for finding in findings}, {"source-text"})
        self.assertEqual(
            [(Path(finding["path"]).name, finding["line"]) for finding in findings],
            [
                ("example.json", 3),
                ("example.json", 5),
                ("example.json", 5),
                ("example.json", 5),
                ("view.js", 2),
                ("view.py", 2),
                ("view.py", 3),
                ("view.py", 4),
                ("example.openapi.yaml", 3),
                ("example.openapi.yaml", 5),
            ],
        )
        self.assertTrue(any("Kayıt yok" in finding["message"] for finding in findings))

    def test_accepts_descriptive_english_name(self):
        self.record(
            "platform_core/doctype/plt_example/plt_example.json",
            doctype="DocType",
            name="PLT Example",
            module="Platform Core",
            fields=[{"fieldname": "record_status", "fieldtype": "Select", "options": "Open\nClosed"}],
        )
        self.assertEqual(self.run_gate(), (0, set()))

    def test_source_text_ignores_markdown_code_without_hiding_turkish_prose(self):
        self.write(
            self.root / "backend/contracts/example.openapi.yaml",
            "openapi: 3.1.0\ninfo:\n"
            "  summary: Read `x-durum` and `yalniz-onay-katmani`.\n"
            "  description: >-\n"
            "    See `contracts/platform_core-kimlik.openapi.yaml`.\n"
            "paths:\n  /status:\n    get:\n"
            "      summary: ``x-durum`` için kayıt getir.\n",
        )
        status, findings = self.gate_findings("--source-text")
        self.assertEqual(status, 1)
        self.assertEqual([finding["line"] for finding in findings], [9])
        self.assertIn("kayıt getir", findings[0]["message"])

    def test_rejects_wrong_metadata_and_glossary_names(self):
        self.record(
            "platform_core/doctype/example/example.json",
            doctype="DocType",
            name="Example",
            module="platform core",
            fields=[{"fieldname": "Bad_Field", "fieldtype": "Select", "options": "Açık"}],
        )
        self.record(
            "fixtures/custom_field.json",
            doctype="Custom Field",
            fieldname="custom_other_name",
        )
        self.assertEqual(
            self.run_gate(),
            (1, {"record-prefix", "module-match", "field-name", "select-name", "glossary", "custom-field"}),
        )

    def test_rejects_python_binding_and_banned_names(self):
        self.write(
            self.package / "policy.py",
            "from frappe import _\n\ndef read_invoice(_):\n"
            "    invoice_data = 1\n    cache_new = invoice_data\n    return cache_new\n",
        )
        self.assertEqual(self.run_gate(), (1, {"translation-binding", "discouraged-name"}))

    def test_legacy_requires_specific_map_entry(self):
        self.record(
            "platform_core/doctype/old_example/old_example.json",
            doctype="DocType",
            name="Old Example",
            module="Platform Core",
            fields=[{"fieldname": "Bad_Field"}],
        )
        self.write(
            self.root / "map.json",
            json.dumps([{"old": "Old Example", "new": "PLT Example", "type": "doctype"}]),
        )
        result, rules = self.run_gate("--legacy", "--map", str(self.root / "map.json"))
        self.assertEqual((result, rules), (1, {"field-name"}))

    def test_detects_workflow_states_and_nested_custom_fields(self):
        self.record(
            "fixtures/workflow.json",
            doctype="Workflow",
            states=[{"state": "Açık"}],
            transitions=[{"state": "Open", "next_state": "Closed"}],
        )
        self.record(
            "platform_core/custom/invoice.json",
            doctype="Invoice",
            custom_fields=[{"fieldname": "custom_wrong_tag"}],
        )
        self.assertEqual(self.run_gate(), (1, {"workflow-state", "custom-field"}))

    def test_detects_scrub_collision_across_records(self):
        self.write(
            self.app / "docs/glossary.yaml",
            "- doctype: PLT Example Label\n- doctype: PLT Example-Label\n",
        )
        for folder, name in (("first", "PLT Example Label"), ("second", "PLT Example-Label")):
            self.record(
                f"platform_core/doctype/{folder}/{folder}.json",
                doctype="DocType",
                name=name,
                module="Platform Core",
            )
        self.assertEqual(self.run_gate(), (1, {"doctype-collision"}))

    def test_reports_turkish_roots_and_names_outside_apps(self):
        self.write(
            self.app / "docs/glossary.yaml",
            '- term_tr: "Müşteri Talebi"\n  doctype: PLT Example\n',
        )
        self.write(
            self.root / "map.json",
            json.dumps([{"old": "odak_kaydi", "new": "focus_record", "type": "identifier"}]),
        )
        self.write(
            self.root / "backend/libs/sample.py",
            "def read_record(record):\n    return record.yeni_musteri_talebi\n",
        )
        self.write(
            self.root / "backend/identity/view.ts",
            "// const musteriTalebi = 1;\n"
            "const caption = 'odak_kaydi';\n"
            "const yeniOdak = record.yeniMusteri;\n"
            "const matchingText = /Müşteri Talebi/;\n",
        )
        self.write(
            self.root / "backend/identity/page.html",
            '<p id="musteri-talebi" class="normal yeni-odak">Müşteri Talebi</p>\n'
            "<p title=\"The example uses id='musteri-talebi'\">Müşteri Talebi</p>\n",
        )
        status, findings = self.gate_findings("--map", str(self.root / "map.json"))
        self.assertEqual(status, 1)
        self.assertEqual(
            {(Path(item["path"]).name, item["line"], item["rule"]) for item in findings},
            {
                ("sample.py", 2, "turkish-name"),
                ("view.ts", 3, "turkish-name"),
                ("page.html", 1, "turkish-name"),
            },
        )
        self.assertEqual(len(findings), 5)

    def test_doctype_copy_uses_glossary_for_ascii_turkish(self):
        self.write(self.app / "docs/glossary.yaml", "- term_tr: Müşteri Talebi\n  doctype: PLT Example\n")
        self.record(
            "platform_core/doctype/plt_example/plt_example.json",
            doctype="DocType",
            name="PLT Example",
            module="Platform Core",
            fields=[{"fieldname": "request_label", "label": "Musteri Talebi"}],
        )
        self.assertEqual(self.run_gate(), (1, {"doctype-copy"}))

    def test_changed_files_mode_checks_only_changed_files(self):
        unchanged = self.root / "backend/dev/unchanged.py"
        self.write(unchanged, "kayit = 1\n")
        subprocess.run(["git", "-C", str(self.root), "add", "backend"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "commit",
                "-m",
                "Deneme tabanını oluştur",
            ],
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "karacaismail",
                "GIT_AUTHOR_EMAIL": "35493655+karacaismail@users.noreply.github.com",
                "GIT_COMMITTER_NAME": "karacaismail",
                "GIT_COMMITTER_EMAIL": "35493655+karacaismail@users.noreply.github.com",
            },
        )
        self.write(self.root / "backend/dev/changed.py", "giris = 1\n")
        status, findings = self.gate_findings("--changed-files")
        self.assertEqual(status, 1)
        self.assertEqual([Path(item["path"]).name for item in findings], ["changed.py"])

    def test_arrow_callback_regex_is_not_treated_as_code_names(self):
        self.write(
            self.root / "backend/identity/security.spec.ts",
            "const matches = lines.filter((line) => /[çğıöşüÇĞİÖŞÜ]|Kullanım|Yalnız/.test(line));\n"
            "const kullanım = matches.length;\n",
        )
        _, findings = self.gate_findings()
        relevant = [item for item in findings if item["rule"] == "turkish-name"]
        self.assertEqual([item["line"] for item in relevant], [2])
