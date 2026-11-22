"""Acceptance checks against a real, pinned and unmodified Press Bench.

Set PRESS_TEST_UNPATCHED_BENCH inside the candidate image. Failures stay failures:
these tests do not patch imports, catch compatibility errors, or mark them expected.
"""

import ast
import os
import shutil
import subprocess
import unittest
from pathlib import Path


def require_executable(name):
    executable = shutil.which(name)
    if executable is None:
        raise AssertionError(f"Required executable not found: {name}")
    return str(Path(executable).absolute())


def contains_patch_marker(path):
    marker = b"press-local:"
    previous = b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            content = previous + chunk
            if marker in content:
                return True
            previous = content[-(len(marker) - 1) :]
    return False


def find_runtime_patch_artifacts(bench, image_root=Path("/")):
    artifacts = []
    for relative in ("opt/press-local/development-image", "opt/press-local/scripts/patch-py314.sh"):
        path = image_root / relative
        if path.exists() or path.is_symlink():
            artifacts.append(path)
    package_roots = sorted(
        path for path in (bench / "env").glob("lib*/python*/site-packages") if path.is_dir()
    )
    if not package_roots:
        raise AssertionError(f"Bench site-packages directory not found under {bench}")
    for package_root in package_roots:
        for path in package_root.rglob("*"):
            if path.name.endswith(".orig") or (path.is_file() and contains_patch_marker(path)):
                artifacts.append(path)
    return sorted(set(artifacts))


@unittest.skipUnless(os.getenv("PRESS_TEST_UNPATCHED_BENCH"), "Set PRESS_TEST_UNPATCHED_BENCH")
class UnpatchedRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.bench = Path(os.environ["PRESS_TEST_UNPATCHED_BENCH"]).absolute()
        self.source = self.bench / "apps" / "press"

    def run_python(self, code):
        completed = subprocess.run(
            [str(self.bench / "env/bin/python"), "-B", "-c", code],
            cwd=self.bench / "sites",
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_press_source_is_pristine(self):
        git_executable = require_executable("git")
        revision = subprocess.check_output(
            [git_executable, "-C", str(self.source), "rev-parse", "HEAD"], text=True, shell=False
        ).strip()
        expected = os.getenv("PRESS_TEST_EXPECTED_REVISION", "7a4384d5eec9f0f0dce4124e9dd48b106e51222f")
        self.assertRegex(expected, r"^[0-9a-f]{40}\Z", "Pin a complete upstream commit SHA.")
        self.assertEqual(revision, expected)
        completed = subprocess.run(
            [git_executable, "-C", str(self.source), "diff", "--exit-code", "HEAD", "--"],
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        status = subprocess.check_output(
            [git_executable, "-C", str(self.source), "ls-files", "--others", "--exclude-standard"],
            text=True,
            shell=False,
        )
        self.assertEqual(status, "", "Unexpected files in the Press checkout: " + status)

    def test_runtime_contains_no_patch_artifacts(self):
        artifacts = find_runtime_patch_artifacts(self.bench)
        self.assertEqual(artifacts, [], "Runtime patch artifacts found: " + ", ".join(map(str, artifacts)))

    def test_dependencies_are_consistent(self):
        uv_executable = require_executable("uv")
        completed = subprocess.run(
            [uv_executable, "pip", "check", "--python", str(self.bench / "env/bin/python")],
            cwd=self.bench,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_press_cookies_imports(self):
        self.run_python("import press.api.cookies")

    def test_python_and_frappe_versions(self):
        self.run_python(
            "import sys, frappe; assert sys.version_info[:2] == (3, 14); "
            "assert frappe.__version__.startswith('16.')"
        )

    def test_press_runner_imports(self):
        self.run_python("import press.runner")

    def test_deploy_candidate_imports(self):
        self.run_python("import press.press.doctype.deploy_candidate.cache_utils")

    def test_product_trial_request_imports(self):
        self.run_python("import press.saas.doctype.product_trial_request.product_trial_request")

    def test_telegram_and_stripe_import_without_patching(self):
        self.run_python("import telegram, stripe; from telegram import Bot, ParseMode")

    def test_removed_standard_modules_import(self):
        self.run_python("import imghdr, pipes, cgi, crypt")

    def test_ansible_collection_loader_runs_local_task(self):
        completed = subprocess.run(
            [
                str(self.bench / "env/bin/ansible-playbook"),
                "-i",
                "localhost,",
                str(Path(__file__).with_name("provisioning_probe.yml")),
            ],
            cwd=self.bench,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("failed=0", completed.stdout)

    def test_original_typed_dict_definition_runs(self):
        source_path = self.source / "press/press/doctype/deploy_candidate/cache_utils.py"
        source = source_path.read_text()
        statement = next(
            (
                node
                for node in ast.parse(source).body
                if (isinstance(node, ast.ClassDef) and node.name == "CommandOutput")
                or (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "CommandOutput"
                        for target in node.targets
                    )
                )
            ),
            None,
        )
        if statement is None:
            self.skipTest("The selected source has no top-level CommandOutput declaration.")
        # Execute the unchanged prefix, keeping source imports, aliases and prerequisites.
        self.run_python("\n".join(source.splitlines()[: statement.end_lineno]))

    def test_original_telemetry_import_exists(self):
        source_path = self.source / "press/saas/doctype/product_trial_request/product_trial_request.py"
        source = source_path.read_text()
        imports = [
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.ImportFrom) and node.module == "frappe.utils.telemetry"
        ]
        if not imports:
            self.skipTest("The selected source has no top-level telemetry import.")
        self.run_python("\n".join(ast.get_source_segment(source, node) for node in imports))


if __name__ == "__main__":
    unittest.main(verbosity=2)
