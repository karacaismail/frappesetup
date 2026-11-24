"""Press must wait longer than identity-sync needs to answer an account deletion (H-5, O-27).

identity-sync answers within its anonymize timeout plus RECORD_GRACE_SECONDS for the outcome records.
Press gives up after its own deletion timeout and then tells the customer that the deletion goes on.
The two services keep these numbers in their own code. This test reads both and compares them, for
the defaults and for the largest allowed values. The files are parsed, not imported: the Press module
needs Frappe.
"""

import ast
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PRESS = BACKEND / "apps/press_tr/press_tr/press_identity/deletion.py"
SERVICE_CONFIG = BACKEND / "identity/identity_sync/identity_sync/config.py"
SERVICE_PIPELINE = BACKEND / "identity/identity_sync/identity_sync/pipeline.py"


def constants(path):
    """The module-level number constants of a Python file."""
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value.value, (int, float)):
                    found[target.id] = node.value.value
    return found


class DeletionTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.press = constants(PRESS)
        config = constants(SERVICE_CONFIG)
        grace = constants(SERVICE_PIPELINE)["RECORD_GRACE_SECONDS"]
        self.service_default = config["DEFAULT_ANONYMIZE_TIMEOUT"] + grace
        self.service_max = config["MAX_ANONYMIZE_TIMEOUT"] + grace

    def test_press_waits_longer_than_the_service_answers_by_default(self):
        self.assertGreater(self.press["DEFAULT_DELETION_TIMEOUT"], self.service_default)

    def test_press_largest_wait_covers_the_service_largest_answer(self):
        self.assertGreaterEqual(self.press["MAX_DELETION_TIMEOUT"], self.service_max)


if __name__ == "__main__":
    unittest.main()
