"""Exercise the branch command in an isolated Git repository."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NAMING = Path(__file__).resolve().parents[1]
MESSAGE = "refactor(naming): D-14 ad eşleşmesini uygula"


class BranchCommandTests(unittest.TestCase):
    def setUp(self):
        scratch = NAMING.parents[2] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name)
        self.root = workspace / "repo"
        self.root.mkdir()
        self.tools = workspace / "tools"
        self.tools.mkdir()
        self.command = self.tools / "apply-to-branch"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.git("init", "-q", "-b", "backend")
        self.git("config", "user.name", "karacaismail")
        self.git("config", "user.email", "35493655+karacaismail@users.noreply.github.com")
        (self.root / "backend").mkdir()
        self.target = self.root / "backend" / "sample.py"
        self.target.write_text("legacy = True\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Deneme tabanını oluştur")
        self.git("switch", "-qc", "fix/sample")
        (self.tools / "apply_renames.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "path = Path('backend/sample.py')\n"
            "if '--check-modules' in sys.argv:\n"
            "    raise SystemExit(int('legacy' in path.read_text()))\n"
            "path.write_text(path.read_text().replace('legacy', 'current'))\n"
        )
        (self.tools / "check_names.py").write_text(
            "from pathlib import Path\n"
            "raise SystemExit(int('current' not in Path('backend/sample.py').read_text()))\n"
        )
        self.env["PYTHON"] = sys.executable

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, env=self.env, check=True, text=True, capture_output=True
        ).stdout.strip()

    def run_command(self, code=""):
        original = NAMING / "apply-to-branch"
        if not original.is_file():
            self.fail("apply-to-branch does not exist")
        shutil.copy2(original, self.command)
        return subprocess.run(
            [str(self.command), "--", sys.executable, "-c", code],
            cwd=self.root,
            env={**self.env, "GIT_COMMITTER_NAME": "Pane", "GIT_COMMITTER_EMAIL": "pane@example.test"},
            capture_output=True,
            text=True,
        )

    def test_success_commits_once_and_repeats_without_commit(self):
        initial = self.git("rev-parse", "HEAD")
        check = "from pathlib import Path; assert 'current' in Path('backend/sample.py').read_text()"
        first = self.run_command(check)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), MESSAGE)
        self.assertEqual(self.git("rev-list", "--count", f"{initial}..HEAD"), "1")
        self.assertEqual(self.git("status", "--porcelain"), "")
        first_head = self.git("rev-parse", "HEAD")
        second = self.run_command(check)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), first_head)

    def test_dirty_worktree_stops_before_apply(self):
        (self.root / "untracked.txt").write_text("keep me")
        outcome = self.run_command()
        self.assertNotEqual(outcome.returncode, 0)
        self.assertIn("clean", outcome.stderr.lower())
        self.assertEqual(self.target.read_text(), "legacy = True\n")

    def test_missing_backend_commit_stops_before_apply(self):
        self.git("switch", "-q", "backend")
        self.git("commit", "--allow-empty", "-qm", "Tabanı ilerlet")
        self.git("switch", "-q", "fix/sample")
        outcome = self.run_command()
        self.assertNotEqual(outcome.returncode, 0)
        self.assertIn("backend", outcome.stderr.lower())
        self.assertEqual(self.target.read_text(), "legacy = True\n")

    def test_failed_test_creates_no_commit(self):
        initial = self.git("rev-parse", "HEAD")
        outcome = self.run_command("raise SystemExit(7)")
        self.assertEqual(outcome.returncode, 7, outcome.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), initial)

    def use_real_name_checker(self, source):
        shutil.copy2(NAMING / "check_names.py", self.tools)
        (self.tools / "rename-map.json").write_text(
            '[{"old":"obsolete","new":"replacement_name","type":"identifier"}]\n'
        )
        self.target.write_text(source)
        self.git("add", ".")
        self.git("commit", "-qm", "Ad denetimi örneğini ekle")

    def test_mapped_legacy_name_stops_before_tests(self):
        self.use_real_name_checker("legacy = True\nobsolete = True\n")
        initial = self.git("rev-parse", "HEAD")
        outcome = self.run_command("print('branch tests ran')")
        self.assertNotEqual(outcome.returncode, 0)
        self.assertIn("Error:", outcome.stdout)
        self.assertIn("[legacy-name]", outcome.stdout)
        self.assertNotIn("branch tests ran", outcome.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD"), initial)

    def test_general_name_warnings_are_reported_and_allow_commit(self):
        self.use_real_name_checker("legacy = True\nresult = True\n")
        outcome = self.run_command("print('branch tests ran')")
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertIn("Warning:", outcome.stdout)
        self.assertIn("[discouraged-name]", outcome.stdout)
        self.assertIn("branch tests ran", outcome.stdout)
        self.assertEqual(self.git("log", "-1", "--format=%s"), MESSAGE)

    def test_test_side_effects_are_never_committed(self):
        initial = self.git("rev-parse", "HEAD")
        outcome = self.run_command("from pathlib import Path; Path('backend/generated.py').touch()")
        self.assertNotEqual(outcome.returncode, 0)
        self.assertIn("changed", outcome.stderr.lower())
        self.assertEqual(self.git("rev-parse", "HEAD"), initial)


class TransitionInstructionsTests(unittest.TestCase):
    def test_backend_instructions_require_clean_tree_and_direct_application(self):
        decision = NAMING.parents[1] / "docs/kararlar/0009-naming-history-fix.md"
        instructions = decision.read_text().split("## Dalda uygulama", 1)[1]
        orchestrator = instructions.split("### İşçi dalı", 1)[0]
        clean_guard = 'test -z "$(git status --porcelain=v1 --untracked-files=all)"'
        apply = 'python3.14 -B backend/dev/naming/apply_renames.py --repo "$PWD"'
        self.assertIn(clean_guard + " &&", orchestrator)
        self.assertIn(apply + " --dry-run", orchestrator)
        self.assertIn(apply + "\n", orchestrator)
        self.assertNotIn("apply-to-branch --", orchestrator)
