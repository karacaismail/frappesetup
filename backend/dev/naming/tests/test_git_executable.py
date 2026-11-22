"""Regression checks for Git executable discovery in naming commands."""

import runpy
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

NAMING = Path(__file__).resolve().parents[1]


class GitExecutableTests(unittest.TestCase):
    def test_commands_explain_missing_git(self):
        for script in ("apply_renames.py", "check_names.py"):
            with (
                self.subTest(script=script),
                patch("shutil.which", return_value=None),
                patch.object(sys, "argv", [script]),
                patch("subprocess.run") as run,
                redirect_stderr(StringIO()) as stderr,
            ):
                with self.assertRaises(SystemExit) as error:
                    runpy.run_path(str(NAMING / script), run_name="__main__")
                self.assertEqual(error.exception.code, 2)
                self.assertIn("Git executable not found on PATH", stderr.getvalue())
                run.assert_not_called()

    def test_git_calls_reuse_the_resolved_absolute_path(self):
        executable = "/example/bin/git"
        for script, functions in (
            ("apply_renames.py", ("git",)),
            ("check_names.py", ("git_output", "changed_files")),
        ):
            with (
                self.subTest(script=script),
                patch("shutil.which", return_value=executable) as discover,
                patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="")) as run,
            ):
                namespace = runpy.run_path(str(NAMING / script))
                for function in functions:
                    namespace[function](NAMING, "HEAD")
                self.assertGreaterEqual(run.call_count, len(functions))
                self.assertTrue(all(call.args[0][0] == executable for call in run.call_args_list))
                discover.assert_called_once_with("git")
