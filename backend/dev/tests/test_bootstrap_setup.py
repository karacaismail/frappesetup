import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bootstrap import complete_local_setup

sys.path.pop(0)


class TestLocalSetup(unittest.TestCase):
    def test_erpnext_setup_completes_system_settings(self):
        frappe = Mock()
        frappe.db.get_single_value.side_effect = ["0", 1]
        wizard = ModuleType("frappe.desk.page.setup_wizard.setup_wizard")
        wizard.setup_complete = Mock(return_value={"status": "ok"})
        with patch.dict(sys.modules, {wizard.__name__: wizard}):
            complete_local_setup(frappe)

        args = wizard.setup_complete.call_args.args[0]
        self.assertEqual(
            (args["language"], args["country"], args["timezone"], args["currency"]),
            ("tr", "Türkiye", "Europe/Istanbul", "TRY"),
        )
        self.assertEqual(args["chart_of_accounts"], "Turkey - Chart of Accounts")
        self.assertEqual(args["enable_telemetry"], 0)
        self.assertTrue(args["fy_start_date"].endswith("-01-01"))
        self.assertTrue(args["fy_end_date"].endswith("-12-31"))
        self.assertEqual(frappe.db.get_single_value.call_count, 2)
        frappe.db.get_single_value.assert_called_with("System Settings", "setup_complete")
        frappe.db.commit.assert_called_once()

    def test_incomplete_setup_fails_bootstrap(self):
        frappe = Mock()
        frappe.db.get_single_value.return_value = 0
        wizard = ModuleType("frappe.desk.page.setup_wizard.setup_wizard")
        wizard.setup_complete = Mock()
        with patch.dict(sys.modules, {wizard.__name__: wizard}):
            with self.assertRaisesRegex(RuntimeError, "setup_complete"):
                complete_local_setup(frappe)

    def test_completed_site_keeps_existing_settings(self):
        frappe = Mock()
        frappe.db.get_single_value.return_value = "1"
        complete_local_setup(frappe)
        frappe.db.commit.assert_not_called()
