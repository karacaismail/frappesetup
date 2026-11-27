"""Tests for scripts/standards-copy-check.py (Kapı 4b, AJA-1344).

Each test builds a throwaway repository and a throwaway shared folder in a
temporary directory, then runs the gate as a subprocess. Exit codes:
0 = all copies equal, 1 = a finding, 2 = the gate could not finish.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "standards-copy-check.py"
NOT_RULES = ["README.md", "KARARLAR.md", "kopyalar.json"]


class CopyCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.std = self.repo / "docs" / "standartlar"
        self.std.mkdir(parents=True)
        self.copies = self.tmp / "references"
        self.copies.mkdir()
        for name in ("a.md", "b.md"):
            (self.std / name).write_text(f"# {name}\nkural\n", encoding="utf-8")
            (self.copies / name).write_text(f"# {name}\nkural\n", encoding="utf-8")
        for name in NOT_RULES[:-1]:
            (self.std / name).write_text("not\n", encoding="utf-8")
        self.write_map(
            {
                "version": 1,
                "copies": [
                    {"source": "docs/standartlar/a.md", "copy": "a.md"},
                    {"source": "docs/standartlar/b.md", "copy": "b.md"},
                ],
                "notRules": NOT_RULES,
            }
        )

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_map(self, data):
        text = data if isinstance(data, str) else json.dumps(data)
        (self.std / "kopyalar.json").write_text(text, encoding="utf-8")

    def run_gate(self, copies=None):
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--root", str(self.repo),
             "--copies", str(copies or self.copies)],
            capture_output=True, text=True,
        )

    def assertExit(self, result, code, needle=None):
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, code, out)
        if needle:
            self.assertIn(needle, out)

    def test_equal_copies_pass(self):
        self.assertExit(self.run_gate(), 0, "2 kopya")

    def test_changed_copy_fails(self):
        with (self.copies / "a.md").open("a", encoding="utf-8") as f:
            f.write("ek satır\n")
        self.assertExit(self.run_gate(), 1, "BULGU: a.md")

    def test_missing_copy_fails(self):
        (self.copies / "b.md").unlink()
        self.assertExit(self.run_gate(), 1, "BULGU: b.md")

    def test_missing_source_fails(self):
        (self.std / "a.md").unlink()
        self.assertExit(self.run_gate(), 1, "BULGU: a.md")

    def test_unmapped_rule_file_fails(self):
        (self.std / "yeni-kural.md").write_text("# yeni\n", encoding="utf-8")
        self.assertExit(self.run_gate(), 1, "BULGU: yeni-kural.md")

    def test_missing_copies_folder_exits_2(self):
        self.assertExit(self.run_gate(self.tmp / "yok"), 2, "KAPI ÇALIŞMADI")

    def test_broken_map_exits_2(self):
        self.write_map("{bozuk")
        self.assertExit(self.run_gate(), 2, "KAPI ÇALIŞMADI")

    def test_map_without_copies_exits_2(self):
        self.write_map({"version": 1, "copies": [], "notRules": NOT_RULES})
        self.assertExit(self.run_gate(), 2, "KAPI ÇALIŞMADI")

    def test_path_outside_folders_exits_2(self):
        self.write_map(
            {
                "version": 1,
                "copies": [{"source": "docs/standartlar/a.md", "copy": "../a.md"}],
                "notRules": NOT_RULES + ["b.md"],
            }
        )
        self.assertExit(self.run_gate(), 2, "KAPI ÇALIŞMADI")

    def test_real_map_lists_every_file(self):
        data = json.loads((ROOT / "docs/standartlar/kopyalar.json").read_text(encoding="utf-8"))
        listed = {Path(c["source"]).name for c in data["copies"]} | set(data["notRules"])
        present = {p.name for p in (ROOT / "docs/standartlar").iterdir() if p.is_file()}
        self.assertEqual(present - listed, set())


if __name__ == "__main__":
    unittest.main()
