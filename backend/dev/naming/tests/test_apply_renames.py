"""Regression tests for the repository rename command."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NAMING = Path(__file__).resolve().parents[1]


class RenameTests(unittest.TestCase):
    def setUp(self):
        scratch = NAMING.parents[2] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)
        self.root = self.workspace / "repo"
        self.root.mkdir()
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            text=True,
            capture_output=True,
            check=True,
        ).stdout

    def write(self, filename, content):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def rename(self, entries, *options):
        mapping = self.workspace / "rename-map.json"
        mapping.write_text(json.dumps(entries), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(NAMING / "apply_renames.py"),
                "--repo",
                str(self.root),
                "--map",
                str(mapping),
                *options,
            ],
            capture_output=True,
            text=True,
        )

    def test_prefixed_doctype_and_path_moves_are_repeatable(self):
        original = "backend/app/legacy/ai_provider.json"
        destination = "backend/app/current/plt_ai_provider.json"
        document = self.write(original, '{"name":"AI Provider","table":"tabAI Provider"}\n')
        use = self.write("backend/app/reference.py", 'provider = "AI Provider"\n')
        self.git("add", ".")
        before = self.git("status", "--porcelain")
        index = self.root / ".git/index"
        before_index = index.read_bytes()
        entries = [
            {"old": "backend/app/legacy", "new": "backend/app/current", "type": "path"},
            {"old": original, "new": destination, "type": "path"},
            {"old": "AI Provider", "new": "PLT AI Provider", "type": "doctype"},
            {"old": "tabAI Provider", "new": "tabPLT AI Provider", "type": "reference"},
        ]

        preview = self.rename(entries, "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn(destination, preview.stdout)
        self.assertEqual(index.read_bytes(), before_index)
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertTrue(document.is_file())
        self.assertFalse((self.root / destination).exists())
        self.assertEqual(use.read_text(), 'provider = "AI Provider"\n')

        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(document.exists())
        self.assertEqual(
            json.loads((self.root / destination).read_text()),
            {"name": "PLT AI Provider", "table": "tabPLT AI Provider"},
        )
        self.assertEqual(use.read_text(), 'provider = "PLT AI Provider"\n')
        before_repeat = self.git("status", "--porcelain"), self.git("diff")

        rerun = self.rename(entries)
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual((self.git("status", "--porcelain"), self.git("diff")), before_repeat)

    def test_only_matching_tracked_backend_references_change(self):
        tracked = self.write(
            "backend/app/hooks.py",
            'from app.kimlik import resolve\nidentities = ("kimlik_api", "other_kimlik")\n',
        )
        fixtures = {
            "backend/other/hooks.py": "from app.kimlik import resolve\n",
            "backend/docs/standartlar/guide.md": "`app.kimlik`\n",
            "backend/app/translations/tr.csv": "app.kimlik,Identity\n",
            "backend/app/locale/tr.po": 'msgid "app.kimlik"\n',
            "src/docs.md": "`app.kimlik`\n",
        }
        for filename, content in fixtures.items():
            self.write(filename, content)
        self.git("add", ".")
        fixtures["backend/app/untracked.py"] = "from app.kimlik import resolve\n"
        self.write("backend/app/untracked.py", fixtures["backend/app/untracked.py"])
        entries = [
            {"old": "kimlik", "new": "identity", "type": "identifier", "paths": ["backend/app/*"]},
            {
                "old": "app.kimlik",
                "new": "app.identity",
                "type": "reference",
                "paths": ["backend/docs/standartlar/*"],
            },
        ]

        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            tracked.read_text(),
            'from app.identity import resolve\nidentities = ("kimlik_api", "other_kimlik")\n',
        )
        for filename, content in fixtures.items():
            with self.subTest(filename=filename):
                self.assertEqual((self.root / filename).read_text(), content)

    def test_collision_fails_before_any_changes(self):
        source = self.write("backend/old.py", "value = 'old'\n")
        destination = self.write("backend/new.py", "value = 'existing'\n")
        unrelated = self.write("backend/unrelated.py", "value = 'old'\n")
        movable = self.write("backend/first.py", "value = 'first'\n")
        self.git("add", ".")
        before = self.git("status", "--porcelain")
        entries = [
            {"old": "backend/first.py", "new": "backend/first_moved.py", "type": "path"},
            {"old": "backend/old.py", "new": "backend/new.py", "type": "path"},
            {"old": "old", "new": "new", "type": "identifier"},
        ]

        for options in [("--dry-run",), ()]:
            with self.subTest(options=options):
                result = self.rename(entries, *options)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("backend/new.py", result.stderr + result.stdout)
                self.assertEqual(self.git("status", "--porcelain"), before)
                self.assertEqual(self.git("diff"), "")
                self.assertTrue(movable.is_file())
                self.assertEqual(source.read_text(), "value = 'old'\n")
                self.assertEqual(destination.read_text(), "value = 'existing'\n")
                self.assertEqual(unrelated.read_text(), "value = 'old'\n")

    def test_tracked_symlink_is_not_read_as_text(self):
        outside = self.workspace / "external.txt"
        outside.write_text("old_name\n", encoding="utf-8")
        link = self.root / "backend/link.txt"
        link.parent.mkdir()
        link.symlink_to(outside)
        self.git("add", ".")

        result = self.rename([{"old": "old_name", "new": "new_name", "type": "identifier"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_text(), "old_name\n")
