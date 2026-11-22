"""Test the AV-72 interface against small Frappe app snapshots."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        subprocess.run(["git", "-C", str(self.root), "add", "backend"], check=True)
        result = subprocess.run(
            [sys.executable, str(CHECK), "--root", str(self.root), "--json", *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode, {finding["rule"] for finding in json.loads(result.stdout)}

    def test_accepts_descriptive_english_name(self):
        self.record(
            "platform_core/doctype/plt_example/plt_example.json",
            doctype="DocType",
            name="PLT Example",
            module="Platform Core",
            fields=[{"fieldname": "record_status", "fieldtype": "Select", "options": "Open\nClosed"}],
        )
        self.assertEqual(self.run_gate(), (0, set()))

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
