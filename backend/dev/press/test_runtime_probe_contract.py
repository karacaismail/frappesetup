"""Regression checks for probing repaired upstream source without rewriting it."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_unpatched_runtime as runtime_probe


class RuntimeProbeContractTest(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[3] / ".pane/scratch/press-py314"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="probe-contract-", dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.bench = Path(temporary.name)
        (self.bench / "env/bin").mkdir(parents=True)
        (self.bench / "env/bin/python").symlink_to(sys.executable)
        (self.bench / "sites").mkdir()
        self.source = self.bench / "apps/press"
        self.packages = self.bench / "env/lib/python3.14/site-packages"
        self.packages.mkdir(parents=True)
        self.image_root = self.bench / "image-root"
        self.tools = self.bench / "tools"
        self.tools.mkdir()

    def probe(self, method, relative_path, source):
        path = self.source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        case = runtime_probe.UnpatchedRuntimeTest(method)
        case.bench = self.bench
        case.source = self.source
        try:
            getattr(case, method)()
        finally:
            self.assertEqual(path.read_text(), source)

    def runtime_case(self, method):
        case = runtime_probe.UnpatchedRuntimeTest(method)
        case.bench = self.bench
        case.source = self.source
        return case

    def write_tool(self, name, exit_code):
        executable = self.tools / name
        executable.write_text(
            f"#!{sys.executable}\nimport sys\nprint('dependency fixture')\nsys.exit({exit_code})\n"
        )
        executable.chmod(0o700)
        return executable

    def test_clean_runtime_has_no_patch_artifacts(self):
        self.assertEqual(runtime_probe.find_runtime_patch_artifacts(self.bench, self.image_root), [])

    def test_image_and_package_patch_artifacts_are_rejected(self):
        artifacts = (
            (self.image_root / "opt/press-local/development-image", b""),
            (self.image_root / "opt/press-local/scripts/patch-py314.sh", b"#!/bin/sh\n"),
            (self.packages / "ansible/module_utils/six/__init__.py.orig", b"backup"),
            (self.packages / "ansible/plugins/loader.py", b"# press-local: patched loader\n"),
            (self.packages / "stripe/cache.bin", b"x" * 65530 + b"press-local:" + b"x"),
            (self.bench / "env/lib64/python3.14/site-packages/other.py", b"# press-local: patch\n"),
        )
        for path, contents in artifacts:
            with self.subTest(path=str(path.relative_to(self.bench))):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
                try:
                    found = runtime_probe.find_runtime_patch_artifacts(self.bench, self.image_root)
                    self.assertIn(path, found)
                finally:
                    path.unlink()

    def test_missing_package_directory_is_not_a_clean_runtime(self):
        self.packages.rmdir()
        with self.assertRaisesRegex(AssertionError, "site-packages"):
            runtime_probe.find_runtime_patch_artifacts(self.bench, self.image_root)

    def test_package_path_must_be_a_directory(self):
        self.packages.rmdir()
        self.packages.write_text("not a package directory")
        with self.assertRaisesRegex(AssertionError, "site-packages"):
            runtime_probe.find_runtime_patch_artifacts(self.bench, self.image_root)

    def test_missing_git_fails_explicitly(self):
        with patch.dict(os.environ, {"PATH": str(self.tools)}):
            with self.assertRaisesRegex(AssertionError, "not found.*git"):
                runtime_probe.require_executable("git")

    def test_git_executable_is_absolute(self):
        executable = self.write_tool("git", 0)
        with patch.dict(os.environ, {"PATH": str(self.tools)}):
            resolved = runtime_probe.require_executable("git")
        self.assertEqual(Path(resolved), executable)
        self.assertTrue(Path(resolved).is_absolute())

    def test_dependency_check_failure_is_not_hidden(self):
        self.write_tool("uv", 1)
        with patch.dict(os.environ, {"PATH": str(self.tools)}):
            with self.assertRaisesRegex(AssertionError, "dependency fixture"):
                self.runtime_case("test_dependencies_are_consistent").test_dependencies_are_consistent()

    def test_dependency_check_accepts_a_consistent_environment(self):
        self.write_tool("uv", 0)
        with patch.dict(os.environ, {"PATH": str(self.tools)}):
            self.runtime_case("test_dependencies_are_consistent").test_dependencies_are_consistent()

    def test_cookie_import_failure_is_not_hidden(self):
        package = self.bench / "sites/press/api"
        package.mkdir(parents=True)
        (package.parent / "__init__.py").write_text("")
        (package / "__init__.py").write_text("")
        (package / "cookies.py").write_text("raise ImportError('cookie fixture mismatch')\n")
        with self.assertRaisesRegex(AssertionError, "cookie fixture mismatch"):
            self.runtime_case("test_press_cookies_imports").test_press_cookies_imports()

    def test_cookie_import_accepts_a_working_module(self):
        package = self.bench / "sites/press/api"
        package.mkdir(parents=True)
        (package.parent / "__init__.py").write_text("")
        (package / "__init__.py").write_text("")
        (package / "cookies.py").write_text("READY = True\n")
        self.runtime_case("test_press_cookies_imports").test_press_cookies_imports()

    def test_class_based_typed_dict_keeps_its_source_import(self):
        self.probe(
            "test_original_typed_dict_definition_runs",
            "press/press/doctype/deploy_candidate/cache_utils.py",
            "from typing import TypedDict as OutputType\nclass CommandOutput(OutputType):\n    cwd: str\n",
        )

    def test_functional_typed_dict_keeps_its_source_import(self):
        self.probe(
            "test_original_typed_dict_definition_runs",
            "press/press/doctype/deploy_candidate/cache_utils.py",
            "import typing as source_typing\n"
            "CommandOutput = source_typing.TypedDict('CommandOutput', {'cwd': str})\n",
        )

    def test_removed_telemetry_import_is_not_applicable(self):
        with self.assertRaisesRegex(unittest.SkipTest, "telemetry"):
            self.probe(
                "test_original_telemetry_import_exists",
                "press/saas/doctype/product_trial_request/product_trial_request.py",
                "def capture_event():\n    return None\n",
            )

    def test_retained_telemetry_import_failure_is_not_hidden(self):
        with self.assertRaisesRegex(AssertionError, "ImportError|ModuleNotFoundError"):
            self.probe(
                "test_original_telemetry_import_exists",
                "press/saas/doctype/product_trial_request/product_trial_request.py",
                "from frappe.utils.telemetry import missing_probe_contract_symbol\n",
            )

    def test_invalid_typed_dict_declaration_still_fails(self):
        with self.assertRaisesRegex(AssertionError, "NameError"):
            self.probe(
                "test_original_typed_dict_definition_runs",
                "press/press/doctype/deploy_candidate/cache_utils.py",
                "from typing import TypedDict\n"
                "CommandOutput = TypedDict('CommandOutput', {'cwd': MissingType})\n",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
