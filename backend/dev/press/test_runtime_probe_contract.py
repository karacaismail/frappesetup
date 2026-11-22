"""Regression checks for probing repaired upstream source without rewriting it."""

import sys
import tempfile
import unittest
from pathlib import Path

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
