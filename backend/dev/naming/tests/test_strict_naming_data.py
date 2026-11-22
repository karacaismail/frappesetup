"""Exercise the naming commands with ambiguous repository data."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NAMING = Path(__file__).resolve().parents[1]


class StrictNamingDataTests(unittest.TestCase):
    def setUp(self):
        scratch = NAMING.parents[2] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        workspace = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        self.sample = self.write("backend/example.py", "legacy = True\n")
        self.mapping = self.write("map.json", "[]\n")
        self.add_backend()

    def write(self, relative, source):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def add_backend(self):
        subprocess.run(["git", "-C", str(self.root), "add", "backend"], check=True)

    def run_command(self, script, root_option, *arguments):
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(NAMING / script),
                root_option,
                str(self.root),
                "--map",
                str(self.mapping),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_rename_rejects_duplicate_map_key_without_writing(self):
        self.mapping.write_text(
            '[{"old":"legacy","new":"first","new":"last","type":"identifier"}]\n', encoding="utf-8"
        )
        result = self.run_command("apply_renames.py", "--repo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate JSON key", result.stderr)
        self.assertEqual(self.sample.read_text(), "legacy = True\n")

    def test_module_scan_rejects_duplicate_allowlist_key(self):
        allowlist = self.write("allowlist.json", '[{"path":"first","path":"last","line_text":"legacy"}]\n')
        result = self.run_command(
            "apply_renames.py", "--repo", "--check-modules", "--module-allowlist", str(allowlist)
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate JSON key", result.stderr)

    def test_isolated_name_checker_rejects_duplicate_map_key(self):
        self.mapping.write_text(
            '[{"old":"legacy","new":"first","new":"last","type":"identifier"}]\n', encoding="utf-8"
        )
        result = self.run_command("check_names.py", "--root")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Duplicate JSON key", result.stderr)

    def test_name_checker_rejects_ambiguous_metadata(self):
        self.write("backend/apps/platform_core/platform_core/modules.txt", "Platform Core\n")
        self.write(
            "backend/apps/platform_core/docs/glossary.yaml", "- term_tr: Örnek\n  doctype: PLT Example\n"
        )
        cases = (
            '"fields":[{"fieldname":"first","fieldname":"last"}]',
            '"fields":[{"fieldname":"example","default":NaN}]',
            '"fields":[{"fieldname":"example","default":Infinity}]',
            '"fields":[{"fieldname":"example","default":-Infinity}]',
        )
        for fields in cases:
            with self.subTest(fields=fields):
                self.write(
                    "backend/apps/platform_core/platform_core/doctype/example/example.json",
                    '{"doctype":"DocType","name":"PLT Example","module":"Platform Core",' + fields + "}\n",
                )
                self.add_backend()
                result = self.run_command("check_names.py", "--root", "--json")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual({finding["rule"] for finding in json.loads(result.stdout)}, {"json"})

    def test_glossary_rejects_duplicate_keys_in_one_entry(self):
        self.write(
            "backend/apps/platform_core/docs/glossary.yaml",
            "- term_tr: Örnek\n  doctype: PLT Example\n  doctype: PLT Other\n",
        )
        self.add_backend()
        result = self.run_command("check_names.py", "--root")
        self.assertEqual(result.returncode, 2)
        self.assertIn("glossary.yaml:3: Duplicate YAML key", result.stderr)

    def test_glossary_rejects_tab_indentation(self):
        self.write(
            "backend/apps/platform_core/docs/glossary.yaml",
            "- term_tr: Örnek\n\tdoctype: PLT Example\n",
        )
        self.add_backend()
        result = self.run_command("check_names.py", "--root")
        self.assertEqual(result.returncode, 2)
        self.assertIn("glossary.yaml:2: YAML indentation must use spaces", result.stderr)

    def test_glossary_accepts_same_key_in_different_entries(self):
        self.write(
            "backend/apps/platform_core/docs/glossary.yaml",
            "- term_tr: Örnek\n  doctype: PLT Example\n- term_tr: Başka\n  doctype: PLT Other\n",
        )
        self.add_backend()
        result = self.run_command("check_names.py", "--root")
        self.assertEqual(result.returncode, 0, result.stderr)
