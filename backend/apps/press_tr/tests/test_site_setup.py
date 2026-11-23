import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1] / "press_tr"


class TestSiteSetup(unittest.TestCase):
    def setUp(self):
        self.frappe = ModuleType("frappe")
        self.frappe.db = Mock()
        self.agent = ModuleType("press.agent")
        self.agent.Agent = Mock()
        upstream = ModuleType("press.press.doctype.site.site")
        upstream.Site = type("Site", (), {})
        spec = importlib.util.spec_from_file_location("site_setup", APP / "site_setup.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {"frappe": self.frappe, self.agent.__name__: self.agent, upstream.__name__: upstream},
        ):
            spec.loader.exec_module(module)
        self.site = module.SetupSite()
        self.site.name = "tenant.example.test"

    def test_dispatches_after_site_is_active(self):
        self.frappe.db.get_value.return_value = ("Active", 0, "test-server")
        self.frappe.db.exists.return_value = None
        args = {"language": "tr", "country": "Türkiye", "currency": "TRY"}
        self.assertIs(
            self.site.complete_setup_wizard(args),
            self.agent.Agent.return_value.complete_setup_wizard.return_value,
        )
        self.agent.Agent.assert_called_once_with("test-server")
        self.agent.Agent.return_value.complete_setup_wizard.assert_called_once_with(self.site, args)

    def test_pending_and_completed_sites_do_not_dispatch(self):
        for status, completed in (("Pending", 0), ("Active", 1)):
            with self.subTest(status=status, completed=completed):
                self.frappe.db.get_value.return_value = (status, completed, "test-server")
                self.assertIsNone(self.site.complete_setup_wizard({}))
        self.agent.Agent.assert_not_called()

    def test_existing_job_prevents_duplicate_dispatch(self):
        self.frappe.db.get_value.return_value = ("Active", 0, "test-server")
        self.frappe.db.exists.return_value = "existing-job"
        self.assertIsNone(self.site.complete_setup_wizard({}))
        self.agent.Agent.assert_not_called()
