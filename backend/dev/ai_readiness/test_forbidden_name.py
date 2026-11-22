"""Check how the scanner handles Git repositories without a usable HEAD."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forbidden_name import git_output, tracked_findings

GATE = Path(__file__).with_name("gate.py").resolve()
SCRATCH = Path(__file__).resolve().parents[3] / ".pane" / "scratch"


class CommitScanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name)
        subprocess.run(["git", "init", "--quiet", self.repository], check=True)
        self.backend = self.repository / "backend"
        self.backend.mkdir()

    def test_gate_rejects_missing_and_relative_git_paths(self):
        tools = self.repository / "tools"
        tools.mkdir()
        (tools / "git").symlink_to(Path(shutil.which("git")).resolve())
        for path in ("", "tools"):
            with self.subTest(path=path):
                result = subprocess.run(
                    [sys.executable, "-B", GATE, "--root", self.backend, "--json"],
                    cwd=self.repository,
                    env=dict(os.environ, PATH=path),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("Git executable", result.stderr)
                self.assertIn("absolute path", result.stderr)

    def test_both_git_calls_use_the_selected_absolute_path(self):
        executable = "/trusted/bin/git"
        with (
            patch("forbidden_name.GIT_EXECUTABLE", executable),
            patch("forbidden_name.subprocess.run") as run,
        ):
            run.side_effect = [
                subprocess.CompletedProcess([], 0, stdout="GIT_DIR\n"),
                subprocess.CompletedProcess([], 0, stdout=b"output"),
            ]
            self.assertEqual(git_output(self.backend, "status"), b"output")
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                [executable, "rev-parse", "--local-env-vars"],
                [executable, "-C", str(self.backend), "status"],
            ],
        )

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
