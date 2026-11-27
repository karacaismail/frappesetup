"""The shared-file gate rejects silent hooks.py overwrites and broken translation CSV files."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

CHECKER = Path(__file__).resolve().parents[1] / "check_shared_files.py"
_spec = importlib.util.spec_from_file_location("check_shared_files", CHECKER)
check_shared_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_shared_files)
HOOKS = "apps/sample_app/sample_app/hooks.py"
CSV = "apps/sample_app/sample_app/translations/tr.csv"


def run_checker(argv):
    # The checker runs in-process. The security gate rejects subprocess use in tests (Bandit B404, B603).
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        returncode = check_shared_files.main(argv)
    return SimpleNamespace(returncode=returncode, stdout=output.getvalue(), stderr="")


class SharedFilesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def check(self):
        return run_checker(["--root", str(self.root)])

    def test_clean_files_pass(self):
        self.write(HOOKS, 'app_name = "sample_app"\nauth_hooks = ["a.b"]\nauth_hooks += ["c.d"]\n')
        self.write(CSV, 'Save,Kaydet,\n"Name, full",Ad,sample.context\n')
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_second_assignment_of_a_hook_fails(self):
        self.write(HOOKS, 'auth_hooks = ["a.b"]\napp_name = "x"\nauth_hooks = ["c.d"]\n')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{HOOKS}:3: auth_hooks", result.stdout)

    def test_annotated_reassignment_fails(self):
        self.write(HOOKS, 'doc_events = {}\ndoc_events: dict = {}\n')
        self.assertEqual(self.check().returncode, 1)

    def test_conflict_marker_in_csv_fails(self):
        self.write(CSV, "Save,Kaydet,\n<<<<<<< HEAD\nOpen,Aç,\n=======\nOpen,Açın,\n>>>>>>> other\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{CSV}:2:", result.stdout)

    def test_csv_row_must_have_three_columns(self):
        self.write(CSV, "Save,Kaydet\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{CSV}:1:", result.stdout)

    def test_duplicate_source_and_context_fails(self):
        self.write(CSV, "Save,Kaydet,\nOpen,Aç,\nSave,Saklayın,\nSave,Kurtar,game\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{CSV}:3:", result.stdout)
        self.assertNotIn(f"{CSV}:4:", result.stdout)

    def test_hooks_with_syntax_error_fails(self):
        self.write(HOOKS, "auth_hooks = [\n")
        self.assertEqual(self.check().returncode, 1)

    def test_real_backend_passes(self):
        result = run_checker([])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
