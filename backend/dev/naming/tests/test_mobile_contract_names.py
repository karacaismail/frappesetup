"""Check OpenAPI operation names against the reviewed rename map."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RENAMER = Path(__file__).resolve().parents[1] / "apply_renames.py"
MOBILE_OPERATIONS = {
    "mobileV1Register": "registerMobileInstallationV1",
    "mobileV1Revoke": "revokeMobileInstallationV1",
    "mobileV1Activity": "recordMobileActivityV1",
    "mobileV1Push": "pushMobileChangesV1",
    "mobileV1Pull": "pullMobileChangesV1",
    "mobileV1Cleanup": "cleanupMobileDataV1",
    "mobileRevokeUserInstallations": "revokeUserMobileInstallations",
    "mobilePwaV1Register": "registerMobilePwaInstallationV1",
    "mobilePwaV1Revoke": "revokeMobilePwaInstallationV1",
    "mobilePwaV1Activity": "recordMobilePwaActivityV1",
    "mobilePwaV1Push": "pushMobilePwaChangesV1",
    "mobilePwaV1Pull": "pullMobilePwaChangesV1",
    "mobileV1ListInstallations": "listMobileInstallationsV1",
    "mobileV1RevokeInstallation": "revokeOwnedMobileInstallationV1",
    "mobilePwaV1ListInstallations": "listMobilePwaInstallationsV1",
    "mobilePwaV1RevokeInstallation": "revokeOwnedMobilePwaInstallationV1",
}


def contract_text(operation_names):
    return "openapi: 3.1.0\npaths:\n" + "".join(
        f"  /operation-{number}:\n    post:\n      operationId: {operation_name}\n"
        for number, operation_name in enumerate(operation_names, start=1)
    )


class MobileContractNameTests(unittest.TestCase):
    def test_mobile_operation_names_are_unique_and_scoped_to_the_mobile_contract(self):
        old_name = "platform_core-mobil.openapi.yaml"
        new_name = "platform_core-mobile.openapi.yaml"
        expected = tuple(MOBILE_OPERATIONS.values())
        self.assertEqual(len(set(expected)), len(expected))
        scratch = RENAMER.parents[3] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        for current_name in (old_name, new_name):
            with self.subTest(current_name=current_name), tempfile.TemporaryDirectory(dir=scratch) as work:
                root = Path(work)
                contracts = root / "backend/contracts"
                contracts.mkdir(parents=True)
                (contracts / current_name).write_text(contract_text(MOBILE_OPERATIONS), encoding="utf-8")
                unrelated = contracts / "unrelated.openapi.yaml"
                unrelated_text = contract_text(("mobileV1Activity", "mobilePwaV1Register"))
                unrelated.write_text(unrelated_text, encoding="utf-8")
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                subprocess.run(["git", "-C", str(root), "add", "backend"], check=True)
                outcome = subprocess.run(
                    [sys.executable, "-B", str(RENAMER), "--repo", str(root)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
                self.assertEqual((contracts / new_name).read_text(encoding="utf-8"), contract_text(expected))
                self.assertEqual(unrelated.read_text(encoding="utf-8"), unrelated_text)
