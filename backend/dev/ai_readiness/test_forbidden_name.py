"""Check how the scanner handles Git repositories without a usable HEAD."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from forbidden_name import tracked_findings

SCRATCH = Path(__file__).resolve().parents[3] / ".pane" / "scratch"


class CommitScanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name)
        subprocess.run(["git", "init", "--quiet", self.repository], check=True)
        self.backend = self.repository / "backend"
        self.backend.mkdir()

    def test_unborn_branch_has_no_commit_finding(self):
        self.assertEqual(list(tracked_findings(self.backend)), [])

    def test_broken_branch_reports_an_inspection_failure(self):
        branch = subprocess.check_output(
            ["git", "symbolic-ref", "HEAD"], cwd=self.repository, text=True
        ).strip()
        branch_ref = self.repository / ".git" / branch
        branch_ref.parent.mkdir(parents=True, exist_ok=True)
        branch_ref.write_text("invalid reference\n", encoding="ascii")

        self.assertEqual(
            list(tracked_findings(self.backend)),
            [(".", 1, "Could not inspect repository or commit range.")],
        )
