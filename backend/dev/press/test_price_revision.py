"""Exercise the public pricing operation and the Site Plan save guard."""

import importlib
import sys
import unittest
from datetime import date
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

if find_spec("babel") is None:
    raise unittest.SkipTest("Run with Babel 2.16.0, as pinned by Frappe 16.50.0")

# Keep Babel's locale classes loaded while the test replaces Frappe imports.
import babel.dates  # noqa: F401
import babel.numbers  # noqa: F401

APP = Path(__file__).resolve().parents[2] / "apps" / "press_tr"


class Record(SimpleNamespace):
    def get(self, field):
        return getattr(self, field, None)


class ValidationError(Exception):
    pass


def translate(message, **kwargs):
    return message


def reject(message):
    raise ValidationError(message)


class PriceRevisionTest(unittest.TestCase):
    def setUp(self):
        self.original = Mock(price_try=100, price_usd=5, price_inr=0, enabled=1)
        self.original.name = "old"
        self.successor = Mock()
        self.successor.name = "new"
        self.frappe = SimpleNamespace(
            _=translate,
            whitelist=lambda **kwargs: lambda function: function,
            only_for=Mock(),
            get_doc=Mock(),
            copy_doc=Mock(return_value=self.successor),
            sendmail=Mock(),
            get_all=Mock(return_value=["subscriber-a", "subscriber-b"]),
            throw=reject,
            utils=SimpleNamespace(getdate=lambda value=None: value or date(2026, 11, 23), rounded=round),
        )
        self.frappe.db = SimpleNamespace(get_value=Mock(return_value=date(2026, 12, 23)))
        self.contacts = Mock(return_value=["subscriber@example.test"])
        self.notice = Mock()
        self.frappe.get_doc.side_effect = [self.original, self.notice, self.notice]
        self.addCleanup(sys.modules.pop, "press_tr.pricing", None)
        contacts = "press.press.doctype.communication_info.communication_info"
        modules = {
            "frappe": self.frappe,
            contacts: SimpleNamespace(get_communication_info=self.contacts),
        }
        with patch.dict(sys.modules, modules), patch.object(sys, "path", [str(APP), *sys.path]):
            self.pricing = importlib.import_module("press_tr.pricing")

    def change(self, start="2026-12-23", try_price="125.50", usd_price="6"):
        return self.pricing.create_price_revision("old", "new", try_price, usd_price, start)

    def test_creates_disabled_copy_without_editing_the_original(self):
        before = (self.original.price_try, self.original.price_usd, self.original.enabled)
        self.assertEqual(self.change(), "new")
        self.frappe.only_for.assert_called_once_with("System Manager")
        self.frappe.copy_doc.assert_called_once_with(self.original)
        self.successor.insert.assert_called_once_with(set_name="new")
        self.assertEqual(float(self.successor.price_try), 125.50)
        self.assertEqual(self.successor.enabled, 0)
        self.assertEqual((self.original.price_try, self.original.price_usd, self.original.enabled), before)
        self.original.check_permission.assert_called_once_with("read")
        self.original.save.assert_not_called()

    def test_records_each_active_subscriber_team_at_thirty_day_boundary(self):
        self.change()
        self.frappe.get_all.assert_called_once_with(
            "Subscription",
            filters={"plan_type": "Site Plan", "plan": "old", "enabled": 1},
            pluck="team",
            distinct=True,
        )
        notices = [call.args[0] for call in self.frappe.get_doc.call_args_list[1:]]
        self.assertEqual([notice["team"] for notice in notices], ["subscriber-a", "subscriber-b"])
        self.assertEqual(self.frappe.sendmail.call_count, 2)
        self.assertTrue(all(call.kwargs["now"] for call in self.frappe.sendmail.call_args_list))
        for notice in notices:
            self.assertEqual(notice["doctype"], "Press Notification")
            self.assertIn("23 Aralık 2026 Çarşamba", notice["message"])
            self.assertIn("125,50", notice["message"])
            self.assertIn("TRY", notice["message"])

    def test_missing_email_blocks_revision_before_any_writes(self):
        self.contacts.side_effect = [["subscriber@example.test"], []]
        with self.assertRaises(ValidationError):
            self.change()
        self.successor.insert.assert_not_called()
        self.notice.insert.assert_not_called()
        self.frappe.sendmail.assert_not_called()

    def test_rejects_early_assignment_even_when_plan_name_is_known(self):
        subscription = SimpleNamespace(enabled=1, plan_type="Site Plan", plan="new")
        with self.assertRaises(ValidationError):
            self.pricing.reject_early_subscription(subscription)
        self.frappe.db.get_value.assert_called_once_with("Site Plan", "new", "price_effective_date")
        self.frappe.db.get_value.return_value = date(2026, 11, 23)
        self.pricing.reject_early_subscription(subscription)

    def test_rejects_less_than_thirty_days_without_writing(self):
        with self.assertRaises(ValidationError):
            self.change(start="2026-12-22")
        self.frappe.copy_doc.assert_not_called()
        self.notice.insert.assert_not_called()

    def test_rejects_direct_price_changes(self):
        for field in ("price_try", "price_usd", "price_inr"):
            changed = Record(price_try=100, price_usd=5, price_inr=0, enabled=1)
            changed.get_doc_before_save = lambda: self.original
            setattr(changed, field, 200)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.pricing.reject_price_edit(changed)

    def test_denied_role_cannot_read_or_write_plans(self):
        self.frappe.only_for.side_effect = PermissionError
        with self.assertRaises(PermissionError):
            self.change()
        self.frappe.get_doc.assert_not_called()

    def test_requires_a_positive_usd_equivalent_only_for_paid_plans(self):
        for try_price, usd_price in (("100", "0"), ("0", "5")):
            with self.subTest(try_price=try_price), self.assertRaises(ValidationError):
                self.change(try_price=try_price, usd_price=usd_price)
        self.change(try_price="0", usd_price="0")
        self.assertEqual(self.successor.price_try, 0)

    def test_revision_cannot_be_enabled_early_or_have_its_start_date_edited(self):
        old = Record(
            price_try=125, price_inr=0, price_usd=6, price_effective_date=date(2026, 12, 23), enabled=0
        )
        changed = Record(**vars(old), get_doc_before_save=lambda: old)
        changed.enabled = 1
        with self.assertRaises(ValidationError):
            self.pricing.reject_price_edit(changed)
        changed.enabled = 0
        changed.price_effective_date = date(2026, 11, 23)
        with self.assertRaises(ValidationError):
            self.pricing.reject_price_edit(changed)

    def test_try_daily_price_preserves_existing_currency_behavior(self):
        fallback = type("Plan", (), {"get_price_per_day": lambda self, currency: currency})
        controller = type("SitePlan", (self.pricing.SitePlanPricing, fallback), {})
        plan = controller()
        plan.price_try, plan.price_usd, plan.period = 125.5, 6, 30
        self.assertEqual(plan.get_price_per_day("TRY"), 4.18)
        self.assertEqual(plan.get_price_per_day("USD"), "USD")
        self.assertEqual(plan.get_price_per_day("INR"), "INR")

    def test_application_registers_install_and_save_hooks(self):
        with patch.object(sys, "path", [str(APP), *sys.path]):
            hooks = importlib.import_module("press_tr.hooks")
        self.assertEqual(hooks.after_install, "press_tr.pricing_schema.sync_pricing_fields")
        self.assertEqual(hooks.after_migrate, hooks.after_install)
        self.assertEqual(hooks.doc_events["Site Plan"]["validate"], "press_tr.pricing.reject_price_edit")
        self.assertIn("press_tr.pricing.SitePlanPricing", hooks.extend_doctype_class["Site Plan"])
        self.assertEqual(
            hooks.doc_events["Subscription"]["validate"], "press_tr.pricing.reject_early_subscription"
        )

    def test_rejects_missing_try_price_for_existing_paid_plan(self):
        plan = self.pricing.SitePlanPricing()
        plan.price_try, plan.price_usd, plan.period = None, 6, 30
        with self.assertRaises(ValidationError):
            plan.get_price_per_day("TRY")


if __name__ == "__main__":
    unittest.main()
