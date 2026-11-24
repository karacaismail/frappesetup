"""G-9: the press_tr plan set, the trial and the plan limits.

The product owner gave the prices on 24 November 2026. The plan limits are still open, so every
limit stays empty and each plan warns that its limits are missing. The test needs no Frappe
install: ``frappe`` is replaced with an in-memory stub.
"""

import json
import os
import unittest
from datetime import date, timedelta
from pathlib import Path

from plan_stubs import TODAY, FakeFrappe, Rejected, load

CLEANUP_ENTRY = "press_tr.fixture_cleanup.disable_cloud_defaults"
SYNC_ENTRY = "press_tr.plans.sync_plans"
NAMES = {
	"starter": "press-tr-starter",
	"growth": "press-tr-growth",
	"enterprise": "press-tr-enterprise",
	"trial": "press-tr-trial",
}


class PlanSetTest(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe(self)
		self.hooks, self.plans = load(self, self.fake, "press_tr.hooks", "press_tr.plans")

	def site_plans(self):
		return self.fake.records.get("Site Plan", {})

	def test_four_plans_exist_after_migrate(self):
		self.plans.sync_plans()
		self.assertEqual(set(self.site_plans()), set(NAMES.values()))
		titles = {name: row["plan_title"] for name, row in self.site_plans().items()}
		self.assertEqual(
			titles,
			{
				NAMES["starter"]: "Başlangıç",
				NAMES["growth"]: "Büyüme",
				NAMES["enterprise"]: "Kurumsal",
				NAMES["trial"]: "Deneme",
			},
		)
		for row in self.site_plans().values():
			self.assertEqual(row["document_type"], "Site")
			self.assertEqual(row["interval"], "Monthly")
		trial = {name for name, row in self.site_plans().items() if row["is_trial_plan"]}
		self.assertEqual(trial, {NAMES["trial"]})

	def test_new_plans_stay_closed_until_an_operator_opens_them(self):
		# Limits are missing, so migrate must not open a plan to customers on its own.
		self.plans.sync_plans()
		self.assertTrue(all(row["enabled"] == 0 for row in self.site_plans().values()))

	def test_after_migrate_syncs_plans_after_the_cleanup(self):
		steps = self.hooks.after_migrate
		self.assertIsInstance(steps, list)
		self.assertEqual(steps.count(CLEANUP_ENTRY), 1)
		self.assertEqual(steps.count(SYNC_ENTRY), 1)
		# The cleanup closes Press fixtures first. Our plans are not fixtures and stay as they are.
		self.assertLess(steps.index(CLEANUP_ENTRY), steps.index(SYNC_ENTRY))
		self.assertIn(SYNC_ENTRY, self.hooks.after_install)

	def test_press_trial_plan_points_to_our_trial(self):
		self.fake.singles[("Press Settings", "press_trial_plan")] = "Press Trial Plan"
		for _attempt in range(2):
			self.plans.sync_plans()
			self.assertEqual(self.fake.singles[("Press Settings", "press_trial_plan")], NAMES["trial"])

	def test_second_migrate_keeps_existing_plan_records(self):
		self.plans.sync_plans()
		self.site_plans()[NAMES["starter"]].update(price_usd=999, enabled=1)
		inserted = len(self.fake.inserted)
		self.plans.sync_plans()
		# A price changes only through a new plan record, never through migrate.
		self.assertEqual(self.site_plans()[NAMES["starter"]]["price_usd"], 999)
		self.assertEqual(self.site_plans()[NAMES["starter"]]["enabled"], 1)
		self.assertEqual(len(self.fake.inserted), inserted)

	def test_limits_are_empty_and_each_plan_warns(self):
		for plan in self.plans.PLANS:
			with self.subTest(plan=plan["name"]):
				self.assertEqual(set(plan["limits"]), set(self.plans.LIMIT_FIELDS))
				self.assertTrue(all(value is None for value in plan["limits"].values()))
				self.assertEqual(self.plans.missing_limits(plan), list(self.plans.LIMIT_FIELDS))
		warnings = self.plans.sync_plans()
		self.assertEqual(len(warnings), len(self.plans.PLANS))
		for plan, warning in zip(self.plans.PLANS, warnings):
			self.assertIn(plan["title"], warning)
			self.assertIn("missing limits", warning)

	def test_empty_limits_are_not_written_to_press(self):
		self.plans.sync_plans()
		for row in self.site_plans().values():
			self.assertNotIn("max_database_usage", row)
			self.assertNotIn("max_storage_usage", row)

	def test_plan_with_all_limits_does_not_warn(self):
		plan = dict(self.plans.PLANS[0], limits=dict.fromkeys(self.plans.LIMIT_FIELDS, 10))
		self.assertEqual(self.plans.missing_limits(plan), [])

	def test_plan_names_are_not_press_fixture_names(self):
		names = {plan["name"] for plan in self.plans.PLANS}
		self.assertEqual(names, set(NAMES.values()))
		fixture = os.environ.get("PRESS_SITE_PLAN_FIXTURE")
		if fixture:
			press = {row["name"] for row in json.loads(Path(fixture).read_text(encoding="utf-8"))}
			self.assertFalse(names & press)


class EnterprisePlanTest(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe(self, roles=("Press User",))
		(self.plans,) = load(self, self.fake, "press_tr.plans")
		self.fake.roles = ["Administrator", "System Manager"]
		self.plans.sync_plans()
		self.fake.roles = ["Press User"]

	def subscription(self, plan):
		return self.fake.get_doc(
			{"doctype": "Subscription", "plan_type": "Site Plan", "plan": NAMES[plan], "enabled": 1}
		)

	def test_only_operators_see_the_enterprise_plan(self):
		roles = {name: row["roles"] for name, row in self.fake.records["Site Plan"].items()}
		self.assertEqual(roles[NAMES["enterprise"]], [{"role": "System Manager"}])
		for plan in ("starter", "growth", "trial"):
			self.assertEqual(roles[NAMES[plan]], [{"role": "Press User"}])

	def test_customer_cannot_choose_the_enterprise_plan(self):
		with self.assertRaises(Rejected):
			self.plans.reject_operator_plan(self.subscription("enterprise"))
		self.plans.reject_operator_plan(self.subscription("starter"))

	def test_operator_can_open_an_enterprise_tenant(self):
		self.fake.roles = ["System Manager"]
		self.plans.reject_operator_plan(self.subscription("enterprise"))


class TrialTest(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe(self)
		(self.plans,) = load(self, self.fake, "press_tr.plans")
		self.plans.sync_plans()

	def site(self, **values):
		return self.fake.get_doc({"doctype": "Site", **values})

	def test_trial_is_fourteen_days(self):
		self.assertEqual(self.plans.TRIAL_DAYS, 14)
		site = self.site(subscription_plan=NAMES["trial"])
		self.plans.set_trial_end_date(site)
		self.assertEqual(site.trial_end_date, TODAY + timedelta(days=14))

	def test_paid_site_has_no_trial_end_date(self):
		site = self.site(subscription_plan=NAMES["starter"])
		self.plans.set_trial_end_date(site)
		self.assertIsNone(site.get("trial_end_date"))

	def test_existing_trial_end_date_stays(self):
		site = self.site(subscription_plan=NAMES["trial"], trial_end_date=date(2026, 12, 1))
		self.plans.set_trial_end_date(site)
		self.assertEqual(site.trial_end_date, date(2026, 12, 1))

	def test_site_stops_when_the_trial_ends(self):
		yesterday, today = TODAY - timedelta(days=1), TODAY
		self.fake.records["Site"] = {
			"ended": {"plan": NAMES["trial"], "status": "Active", "trial_end_date": yesterday},
			"last-day": {"plan": NAMES["trial"], "status": "Active", "trial_end_date": today},
			"paid": {"plan": NAMES["starter"], "status": "Active", "trial_end_date": None},
			"stopped": {"plan": NAMES["trial"], "status": "Suspended", "trial_end_date": yesterday},
		}
		self.assertEqual(self.plans.suspend_expired_trials(), ["ended"])
		self.assertEqual([name for name, _reason in self.fake.suspended], ["ended"])
		self.assertEqual(self.fake.records["Site"]["last-day"]["status"], "Active")
		self.assertEqual(self.fake.records["Site"]["paid"]["status"], "Active")

	def test_only_operators_stop_trial_sites(self):
		self.fake.roles = ["Press User"]
		with self.assertRaises(PermissionError):
			self.plans.suspend_expired_trials()


class PlanHooksTest(unittest.TestCase):
	def setUp(self):
		(self.hooks,) = load(self, FakeFrappe(self), "press_tr.hooks")

	def test_site_hooks_keep_the_g49_and_g7_lines(self):
		site = self.hooks.doc_events["Site"]
		self.assertEqual(site["validate"], "press_tr.backup_keys.validate_site_keys")
		self.assertEqual(site["on_update"], "press_tr.setup_wizard.start_setup_wizard")
		self.assertEqual(site["before_insert"], "press_tr.plans.set_trial_end_date")

	def test_subscription_hooks_check_price_start_and_operator_plans(self):
		self.assertEqual(
			self.hooks.doc_events["Subscription"]["validate"],
			["press_tr.pricing.reject_early_subscription", "press_tr.plans.reject_operator_plan"],
		)


if __name__ == "__main__":
	unittest.main()
