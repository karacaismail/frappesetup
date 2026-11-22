"""Check the CP2 driver against local fixture worktrees."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NAMING = Path(__file__).resolve().parents[1]


class DriverTests(unittest.TestCase):
    def setUp(self):
        scratch = NAMING.parents[2] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.repo = self.folder / "source repo"
        self.repo.mkdir()
        self.worker = self.folder / "worker with space"
        self.stale = self.folder / "stale worker"
        self.tools = self.folder / "tools"
        self.tools.mkdir()
        self.scratch = self.folder / "copies"
        self.scratch.mkdir()
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_") and key != "PANE_ORCHESTRATION_SESSION_ID"
        }
        self.env["PANE_SCRATCH_DIR"] = str(self.scratch)
        self.git(self.repo, "init", "-qb", "backend")
        self.git(self.repo, "config", "user.name", "karacaismail")
        self.git(self.repo, "config", "user.email", "35493655+karacaismail@users.noreply.github.com")
        (self.repo / "backend").mkdir()
        (self.repo / "backend/example.py").write_text("old_name = True\n")
        self.git(self.repo, "add", "backend")
        self.git(self.repo, "commit", "-qm", "Deneme tabanı")
        self.git(self.repo, "worktree", "add", "-qb", "stale", str(self.stale))
        self.git(self.repo, "commit", "--allow-empty", "-qm", "Tabanı ilerlet")
        self.git(self.repo, "worktree", "add", "-qb", "worker", str(self.worker))
        source = self.tools / "apply_renames.py"
        source.write_text(
            "import sys\nfrom pathlib import Path\n"
            "file = Path('backend/example.py')\n"
            "if '--check-modules' not in sys.argv:\n"
            "    file.write_text(file.read_text().replace('old_name', 'new_name'))\n"
        )
        (self.tools / "check_names.py").write_text("raise SystemExit(0)\n")

    def git(self, root, *args):
        return subprocess.run(
            ["git", *args], cwd=root, env=self.env, check=True, capture_output=True, text=True
        ).stdout.strip()

    def run_driver(self, *args):
        for name in ("run_cp2.py", "apply-to-branch"):
            source = NAMING / name
            if source.exists():
                shutil.copy2(source, self.tools)
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.tools / "run_cp2.py"),
                "--repo",
                str(self.repo),
                *args,
                "--",
                sys.executable,
                "-B",
                "-c",
                "from pathlib import Path; assert 'new_name' in Path('backend/example.py').read_text()",
            ],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_default_reports_every_worktree_without_writing_worker_refs(self):
        initial = self.git(self.repo, "show-ref", "--heads")
        dirty = self.worker / "backend/example.py"
        dirty.write_text("uncommitted = True\n")
        result = self.run_driver()
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "dry-run")
        by_branch = {row["branch"]: row for row in report["worktrees"]}
        self.assertEqual(set(by_branch), {"backend", "worker", "stale"})
        self.assertEqual(by_branch["backend"]["status"], "passed")
        self.assertEqual(by_branch["worker"]["status"], "passed")
        self.assertEqual(by_branch["worker"]["commit"], None)
        self.assertEqual(by_branch["worker"]["changed_files"], 1)
        self.assertEqual(by_branch["stale"]["status"], "failed")
        self.assertIn("Merge the local backend branch", by_branch["stale"]["output"])
        self.assertEqual(self.git(self.repo, "show-ref", "--heads"), initial)
        self.assertEqual(dirty.read_text(), "uncommitted = True\n")
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_apply_requires_the_pane_orchestrator(self):
        result = self.run_driver("--apply")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Pane orchestrator", result.stderr)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_orchestrator_retains_commit_only_in_guarded_copy(self):
        guard = Path.home() / ".config/git/author-guard/hooks"
        effective = subprocess.run(
            ["git", "config", "--path", "--get", "core.hooksPath"],
            cwd=self.folder,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if effective.returncode or Path(effective.stdout.strip()).resolve() != guard.resolve():
            self.skipTest("Requires the user's installed Git author guard.")
        self.env["PANE_ORCHESTRATION_SESSION_ID"] = "fixture-orchestrator"
        initial = self.git(self.repo, "show-ref", "--heads")
        result = self.run_driver("--apply")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        rows = {row["branch"]: row for row in report["worktrees"]}
        self.assertEqual(report["mode"], "apply")
        self.assertEqual(rows["backend"]["mode"], "dry-run")
        worker = rows["worker"]
        self.assertEqual(worker["status"], "passed", worker["output"])
        self.assertEqual(self.git(Path(worker["copy"]), "rev-parse", "HEAD"), worker["commit"])
        self.assertEqual(self.git(Path(worker["copy"]), "remote"), "")
        self.assertEqual(self.git(self.repo, "show-ref", "--heads"), initial)
