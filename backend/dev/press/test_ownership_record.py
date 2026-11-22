"""Keep the Press integration hooks and owned records in the app record."""

import unittest
from pathlib import Path

APP_RECORD = Path(__file__).resolve().parents[2] / "apps" / "press_tr" / "README.md"


class PressOwnershipRecordTest(unittest.TestCase):
    def test_account_events_and_internal_records_are_recorded(self):
        record = APP_RECORD.read_text(encoding="utf-8")
        for entry in ("User.on_update", "on_logout", "PTR Identity Link", "PTR Keycloak Session"):
            with self.subTest(entry=entry):
                self.assertIn(f"`{entry}`", record)
