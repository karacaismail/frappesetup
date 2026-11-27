"""Check that the e2e stack runs inside the shared heavy test lock (AJA-1813)."""

import runpy
import unittest
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
REPOSITORY = SUITE.parents[1]
LOCK = REPOSITORY / "scripts" / "agir-test"


class HeavyTestLockTest(unittest.TestCase):
    def test_stack_start_test_and_stop_share_one_lock(self):
        namespace = runpy.run_path(str(SUITE / "bin" / "merge-preview"))
        runtime = SUITE / "preview" / "runtime.sh"
        worktree = Path("/scratch/preview/worktree")
        command = namespace["live_command"](runtime, worktree)
        self.assertEqual(command[0], str(LOCK))
        self.assertEqual(command[1:], [namespace["BASH_PATH"], str(runtime), str(worktree)])

    def test_lock_script_exists_and_is_executable(self):
        self.assertTrue(LOCK.is_file())
        self.assertTrue(LOCK.stat().st_mode & 0o111)

    def test_container_browser_runner_keeps_the_lock_slot(self):
        runner = (SUITE / "preview" / "run-container.sh").read_text()
        self.assertIn("--env AGIR_TEST_YER", runner)


if __name__ == "__main__":
    unittest.main()
