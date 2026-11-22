"""Check that preview Git calls use the resolved executable."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


def load_merging():
    path = Path(__file__).resolve().parents[1] / "preview" / "merging.py"
    spec = importlib.util.spec_from_file_location("preview_merging", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitResolutionTest(unittest.TestCase):
    def test_resolves_once_and_passes_the_absolute_path_to_every_call(self):
        with patch("shutil.which", return_value="/tools/git") as which:
            merging = load_merging()
            with patch("subprocess.run") as run:
                merging.git(".", "status")
                merging.git(".", "log")

        which.assert_called_once_with("git")
        self.assertEqual([call.args[0][0] for call in run.call_args_list], ["/tools/git", "/tools/git"])

    def test_rejects_missing_and_relative_paths_before_running_git(self):
        for path in (None, "bin/git"):
            with self.subTest(path=path), patch("shutil.which", return_value=path):
                merging = load_merging()
                with patch("subprocess.run") as run:
                    with self.assertRaisesRegex(merging.MergeError, "absolute.*Git"):
                        merging.git(".", "status")
                    run.assert_not_called()
