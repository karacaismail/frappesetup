"""Check how the live preview selects its Bash executable."""

import os
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

COMMAND = Path(__file__).resolve().parents[1] / "bin" / "merge-preview"


def load_preview(bash_path):
    find_executable = shutil.which
    with patch("shutil.which", side_effect=lambda name: bash_path if name == "bash" else find_executable(name)) as find:
        preview = runpy.run_path(str(COMMAND))
    return preview, find


class BashResolutionTest(unittest.TestCase):
    def test_resolves_bash_once_and_launches_with_its_absolute_path(self):
        preview, find = load_preview("/tools/bash")
        with tempfile.TemporaryDirectory(dir=os.environ.get("PANE_SCRATCH_DIR")) as directory:
            root = Path(directory)
            suite = root / "backend" / "e2e"
            suite.mkdir(parents=True)
            (suite / "fake-provider.mjs").touch()
            dependency_bin = root / "node_modules" / ".bin"
            dependency_bin.mkdir(parents=True)
            (dependency_bin / "playwright").touch()
            preview["run_live"].__globals__["SUITE"] = suite
            worktree = root / "worktree"
            with patch("subprocess.Popen") as popen:
                preview["run_live"](worktree, {})
            self.assertEqual(popen.call_args.args[0][0], "/tools/bash")
        self.assertEqual(sum(call.args == ("bash",) for call in find.call_args_list), 1)

    def test_refuses_missing_or_relative_bash_before_preparing_the_worktree(self):
        for bash_path in (None, "tools/bash"):
            with self.subTest(bash_path=bash_path), tempfile.TemporaryDirectory(
                dir=os.environ.get("PANE_SCRATCH_DIR"),
            ) as directory:
                preview, _ = load_preview(bash_path)
                worktree = Path(directory)
                with patch("subprocess.Popen") as popen:
                    with self.assertRaisesRegex(preview["MergeError"], "absolute.*Bash"):
                        preview["run_live"](worktree, {})
                    popen.assert_not_called()
                self.assertEqual(list(worktree.iterdir()), [])
