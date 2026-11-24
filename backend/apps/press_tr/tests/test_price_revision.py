"""G-9: a price change opens a new Site Plan record and moves subscribers on its start day.

Press reads the current plan price when it records usage (``Subscription.create_usage_record``).
So a price is never edited in place. An operator opens a copy with the new price at least 30
days ahead. Each subscriber team gets an email and a Press notification. On the start day the
operator enables the copy by hand. Then subscribers move and the old plan becomes a legacy plan.
No scheduled job is used (PO decision in AJA-136).

The test needs no Frappe install: ``frappe`` and the Press contact lookup are replaced with stubs.
"""

import ast
import importlib
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

APP = Path(__file__).resolve().parents[1]
CONTACTS = "press.press.doctype.communication_info.communication_info"


class Record(SimpleNamespace):
	def get(self, field, default=None):
		return getattr(self, field, default)


class Rejected(Exception):
	pass


def reject(message, *args, **kwargs):
	raise Rejected(message)


class PriceRevisionTest(unittest.TestCase):
	def setUp(self):
		self.original = Mock(price_usd=400, price_inr=0, enabled=1)
		self.original.name = "press-tr-starter"
		self.successor = Mock()
		self.successor.name = "press-tr-starter-2027"
		self.frappe = SimpleNamespace(
			_=lambda message, *args, **kwargs: message,
			only_for=Mock(),
			get_doc=Mock(),
			copy_doc=Mock(return_value=self.successor),
			sendmail=Mock(),
			get_all=Mock(return_value=["subscriber-a", "subscriber-b"]),
			throw=reject,
			utils=SimpleNamespace(getdate=lambda value=None: value or date(2026, 11, 23)),
		)
		self.frappe.db = SimpleNamespace(get_value=Mock(return_value=date(2026, 12, 23)), set_value=Mock())
		self.contacts = Mock(return_value=["subscriber@example.test"])
		self.notice = Mock()
		self.frappe.get_doc.side_effect = [self.original, self.notice, self.notice]
		modules = {"frappe": self.frappe, CONTACTS: SimpleNamespace(get_communication_info=self.contacts)}
		for patcher in (patch.dict(sys.modules, modules), patch.object(sys, "path", [str(APP), *sys.path])):
			patcher.start()
			self.addCleanup(patcher.stop)
		for name in ("press_tr.pricing", "press_tr.plans"):
			sys.modules.pop(name, None)
		self.pricing = importlib.import_module("press_tr.pricing")

	def change(self, start="2026-12-23", price="450", plan="press-tr-starter"):
		return self.pricing.create_price_revision(plan, "press-tr-starter-2027", price, start)

	def test_creates_a_closed_copy_without_editing_the_original(self):
		before = (self.original.price_usd, self.original.price_inr, self.original.enabled)
		self.assertEqual(self.change(), "press-tr-starter-2027")
		self.frappe.only_for.assert_called_once_with("System Manager")
		self.frappe.copy_doc.assert_called_once_with(self.original)
		self.successor.insert.assert_called_once_with(set_name="press-tr-starter-2027")
		self.assertEqual(float(self.successor.price_usd), 450.0)
		self.assertEqual(self.successor.price_inr, 0)
		self.assertEqual(self.successor.enabled, 0)
		self.assertEqual(self.successor.legacy_plan, 0)
		self.assertEqual(self.successor.price_previous_plan, "press-tr-starter")
		self.assertEqual((self.original.price_usd, self.original.price_inr, self.original.enabled), before)
		self.original.save.assert_not_called()

	def test_each_subscriber_team_gets_a_notice_and_an_email(self):
		self.change()
		self.frappe.get_all.assert_called_once_with(
			"Subscription",
			filters={"plan_type": "Site Plan", "plan": "press-tr-starter", "enabled": 1},
			pluck="team",
			distinct=True,
		)
		notices = [entry.args[0] for entry in self.frappe.get_doc.call_args_list[1:]]
		self.assertEqual([notice["team"] for notice in notices], ["subscriber-a", "subscriber-b"])
		self.assertEqual(self.frappe.sendmail.call_count, 2)
		self.assertTrue(all(entry.kwargs["now"] for entry in self.frappe.sendmail.call_args_list))
		for notice in notices:
			self.assertEqual(notice["doctype"], "Press Notification")
			self.assertIn("23 Aralık 2026 Çarşamba", notice["message"])
			self.assertIn("450,00", notice["message"])

	def test_missing_email_blocks_the_change_before_any_write(self):
		self.contacts.side_effect = [["subscriber@example.test"], []]
		with self.assertRaises(Rejected):
			self.change()
		self.successor.insert.assert_not_called()
		self.notice.insert.assert_not_called()
		self.frappe.sendmail.assert_not_called()

	def test_start_must_be_at_least_thirty_days_ahead(self):
		with self.assertRaises(Rejected):
			self.change(start="2026-12-22")
		self.frappe.copy_doc.assert_not_called()
		self.notice.insert.assert_not_called()

	def test_same_price_is_rejected(self):
		with self.assertRaises(Rejected):
			self.change(price="400")
		self.frappe.copy_doc.assert_not_called()

	def test_direct_price_edits_are_rejected(self):
		for field in ("price_usd", "price_inr"):
			changed = Record(price_usd=400, price_inr=0, enabled=1)
			changed.get_doc_before_save = lambda: self.original
			setattr(changed, field, 500)
			with self.subTest(field=field), self.assertRaises(Rejected):
				self.pricing.reject_price_edit(changed)

	def test_only_operators_change_prices(self):
		self.frappe.only_for.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			self.change()
		self.frappe.get_doc.assert_not_called()

	def test_enterprise_plan_gets_no_price(self):
		self.original.name = "press-tr-enterprise"
		self.original.price_usd = 0
		with self.assertRaises(Rejected):
			self.change(plan="press-tr-enterprise")
		self.frappe.copy_doc.assert_not_called()

	def test_copy_cannot_open_early_or_change_its_start_date(self):
		old = Record(price_usd=450, price_inr=0, price_effective_date=date(2026, 12, 23), enabled=0)
		changed = Record(**vars(old), get_doc_before_save=lambda: old)
		changed.enabled = 1
		with self.assertRaises(Rejected):
			self.pricing.reject_price_edit(changed)
		changed.enabled = 0
		changed.price_effective_date = date(2026, 11, 23)
		with self.assertRaises(Rejected):
			self.pricing.reject_price_edit(changed)

	def test_early_assignment_is_rejected(self):
		subscription = SimpleNamespace(enabled=1, plan_type="Site Plan", plan="press-tr-starter-2027")
		with self.assertRaises(Rejected):
			self.pricing.reject_early_subscription(subscription)
		self.frappe.db.get_value.return_value = date(2026, 11, 23)
		self.pricing.reject_early_subscription(subscription)

	def activate(self, today):
		start = date(2026, 12, 23)
		before = Record(enabled=0, price_effective_date=start, price_previous_plan="press-tr-starter")
		revision = Record(**vars(before), name="press-tr-starter-2027", get_doc_before_save=lambda: before)
		revision.enabled = 1
		self.frappe.utils.getdate = lambda value=None: value or today
		self.pricing.reject_price_edit(revision)
		self.pricing.move_subscriptions_on_activation(revision)

	def test_subscribers_stay_on_the_old_plan_the_day_before_start(self):
		subscription = Mock(plan="press-tr-starter", plan_type="Site Plan", enabled=1)
		self.frappe.get_doc.side_effect = None
		self.frappe.get_doc.return_value = subscription
		with self.assertRaises(Rejected):
			self.activate(date(2026, 12, 22))
		self.assertEqual(subscription.plan, "press-tr-starter")
		subscription.save.assert_not_called()
		self.frappe.db.set_value.assert_not_called()

	def test_subscribers_move_on_the_start_day(self):
		subscriber = Mock(plan="press-tr-starter", plan_type="Site Plan", enabled=1)
		already_changed = Mock(plan="press-tr-growth", plan_type="Site Plan", enabled=1)
		self.frappe.get_all.return_value = ["active", "changed"]
		self.frappe.get_doc.side_effect = [subscriber, already_changed]
		self.activate(date(2026, 12, 23))
		self.assertEqual(
			self.frappe.get_doc.call_args_list,
			[call("Subscription", "active", for_update=True), call("Subscription", "changed", for_update=True)],
		)
		self.assertEqual(subscriber.plan, "press-tr-starter-2027")
		subscriber.save.assert_called_once_with()
		self.assertEqual(already_changed.plan, "press-tr-growth")
		already_changed.save.assert_not_called()

	def test_old_plan_becomes_a_legacy_plan_on_the_start_day(self):
		self.frappe.get_all.return_value = []
		self.frappe.get_doc.side_effect = None
		self.activate(date(2026, 12, 23))
		self.frappe.db.set_value.assert_called_once_with(
			"Site Plan",
			"press-tr-starter",
			{"legacy_plan": 1, "allow_downgrading_from_other_plan": 1, "enabled": 0},
		)

	def test_price_change_is_not_an_http_method(self):
		# The operator runs it with "bench execute". The edge proxy keeps Press closed to customers.
		tree = ast.parse((APP / "press_tr/pricing.py").read_text(encoding="utf-8"))
		decorators = [
			ast.unparse(decorator)
			for node in ast.walk(tree)
			if isinstance(node, ast.FunctionDef)
			for decorator in node.decorator_list
		]
		self.assertFalse([decorator for decorator in decorators if "whitelist" in decorator])

	def test_hooks_register_the_save_guards(self):
		hooks = importlib.import_module("press_tr.hooks")
		self.assertEqual(hooks.doc_events["Site Plan"]["validate"], "press_tr.pricing.reject_price_edit")
		self.assertEqual(
			hooks.doc_events["Site Plan"]["on_update"], "press_tr.pricing.move_subscriptions_on_activation"
		)
		self.assertIn("press_tr.pricing_schema.sync_pricing_fields", hooks.after_migrate)
		self.assertIn("press_tr.pricing_schema.sync_pricing_fields", hooks.after_install)


if __name__ == "__main__":
	unittest.main()
