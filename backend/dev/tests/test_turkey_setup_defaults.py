"""Exercise the registered G-41 hooks without a site or a database."""

import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[2] / "apps" / "platform_core"
SYSTEM_SETTINGS = {
    "country": "Türkiye",
    "language": "tr",
    "time_zone": "Europe/Istanbul",
    "currency": "TRY",
    "number_format": "#.###,##",
    "date_format": "dd.mm.yyyy",
    "time_format": "HH:mm",
    "first_day_of_the_week": "Monday",
    "float_precision": "2",
    "currency_precision": "2",
    "rounding_method": "Commercial Rounding",
}
BRAND = "Atonota"
UNTOUCHED = ("Accounts Settings", "Selling Settings", "Buying Settings")


class TurkeySetupDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.system = {"float_precision": "3", "rounding_method": "Banker's Rounding"}
        self.global_defaults = {"default_currency": "USD", "default_company": "Example"}
        self.defaults = {"currency": "USD", "lang": "en"}
        self.currency = {"enabled": 0}
        self.documents = {
            name: Mock(get=values.get, update=values.update)
            for name, values in (
                ("System Settings", self.system),
                ("Global Defaults", self.global_defaults),
            )
        }
        self.clear_settings_cache = Mock()
        self.set_language = Mock(side_effect=lambda lang: self.defaults.update(lang=lang))
        self.frappe = SimpleNamespace(
            db=SimpleNamespace(
                get_default=self.defaults.get,
                set_default=Mock(side_effect=lambda key, value: self.defaults.update({key: value})),
                set_single_value=Mock(side_effect=self.set_single_value),
                get_value=Mock(side_effect=lambda doctype, name, field: self.currency.get(field)),
                set_value=Mock(
                    side_effect=lambda doctype, name, field, value: self.currency.update({field: value})
                ),
            ),
            get_single=self.documents.__getitem__,
            get_installed_apps=Mock(return_value=["frappe", "erpnext", "platform_core"]),
            conf={"identity_brand_name": BRAND},
        )

    def set_single_value(self, doctype, values):
        self.documents[doctype].update(values)

    def run_hook(self, event, *args):
        with patch.object(sys, "path", [str(APP), *sys.path]), patch.dict(
            sys.modules,
            {
                "frappe": self.frappe,
                "frappe.core.doctype.system_settings.system_settings": SimpleNamespace(
                    clear_system_settings_cache=self.clear_settings_cache,
                ),
                "frappe.translate": SimpleNamespace(set_default_language=self.set_language),
            },
        ):
            hooks = importlib.import_module("platform_core.hooks")
            methods = [
                method
                for method in getattr(hooks, event, [])
                if method.startswith("platform_core.config.")
            ]
            self.assertEqual(len(methods), 1, event)
            module, name = methods[0].rsplit(".", 1)
            getattr(importlib.import_module(module), name)(*args)

    def assert_defaults(self):
        self.assertEqual(self.system, SYSTEM_SETTINGS | {"app_name": BRAND})
        self.assertEqual(
            self.global_defaults,
            {"country": "Türkiye", "default_currency": "TRY", "default_company": "Example"},
        )
        self.assertEqual(self.defaults, SYSTEM_SETTINGS | {"lang": "tr"})
        self.assert_erpnext_settings_untouched()
        self.assertEqual(self.currency, {"enabled": 1})
        for doc in self.documents.values():
            doc.save.assert_not_called()

    def assert_erpnext_settings_untouched(self):
        # Accounts, Selling and Buying keep the ERPNext defaults.
        written = {call.args[0] for call in self.frappe.db.set_single_value.call_args_list}
        self.assertFalse(written & set(UNTOUCHED), written)

    def test_wizard_completion_restores_all_defaults(self):
        self.run_hook("setup_wizard_complete", {"country": "Türkiye"})
        self.assert_defaults()
        self.clear_settings_cache.assert_called_once_with()

    def test_migrate_repairs_settings_once(self):
        self.run_hook("after_migrate")
        self.assert_defaults()
        writes = (
            self.frappe.db.set_single_value,
            self.frappe.db.set_default,
            self.set_language,
            self.frappe.db.set_value,
            self.clear_settings_cache,
        )
        for write in writes:
            write.reset_mock()
        self.run_hook("after_migrate")
        for write in writes:
            write.assert_not_called()

    def test_migrate_repairs_stale_global_currency(self):
        self.system.update(SYSTEM_SETTINGS | {"app_name": BRAND})
        self.global_defaults.update(country="Türkiye", default_currency="TRY")
        self.currency["enabled"] = 1
        self.defaults.update(SYSTEM_SETTINGS | {"currency": "USD", "lang": "tr"})
        self.run_hook("after_migrate")
        self.assert_defaults()
        self.frappe.db.set_default.assert_called_once_with("currency", "TRY")
        self.frappe.db.set_single_value.assert_not_called()
        self.clear_settings_cache.assert_not_called()

    def test_migrate_on_frappe_without_erpnext(self):
        self.frappe.get_installed_apps.return_value = ["frappe", "platform_core"]
        self.run_hook("after_migrate")
        self.assertEqual(self.system, SYSTEM_SETTINGS | {"app_name": BRAND})
        self.frappe.db.set_single_value.assert_called_once_with(
            "System Settings", SYSTEM_SETTINGS | {"app_name": BRAND}
        )
        self.frappe.db.get_value.assert_not_called()

    def test_rounding_method_is_commercial(self):
        self.run_hook("after_migrate")
        self.assertEqual(self.system["rounding_method"], "Commercial Rounding")

    def test_app_name_comes_from_identity_brand_name(self):
        self.frappe.conf = {"identity_brand_name": "  Deneme Marka  "}
        self.run_hook("after_migrate")
        self.assertEqual(self.system["app_name"], "Deneme Marka")

    def test_missing_brand_name_leaves_app_name_alone(self):
        for conf in ({}, {"identity_brand_name": ""}, {"identity_brand_name": "   "}):
            with self.subTest(conf=conf):
                self.system.pop("app_name", None)
                self.frappe.conf = conf
                self.run_hook("after_migrate")
                self.assertNotIn("app_name", self.system)
