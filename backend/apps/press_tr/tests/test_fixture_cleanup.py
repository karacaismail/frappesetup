"""G-8: press_tr closes Frappe Cloud defaults after every migrate.

Frappe imports Press fixtures before ``after_migrate`` runs. A fixture with a newer ``modified``
stamp overwrites local edits, so the cleanup must run again on every migrate.

The test needs no Frappe install: ``frappe`` is replaced with an in-memory stub.
"""

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
SIGNUP_METHOD = "press.signup_e2e.run_signup_e2e"
CLEANUP_ENTRY = "press_tr.fixture_cleanup.disable_cloud_defaults"
PRESS_TIERS = ("Beginner", "Growth", "Intermediate", "Advance", "Power", "Elite")


class FakeDatabase:
	"""Stores rows as ``{doctype: {name: {field: value}}}`` and records every write."""

	def __init__(self, test, records):
		self.test = test
		self.records = records
		self.writes = []

	def _matches(self, row, name, filters):
		for field, operator, expected in filters:
			value = name if field == "name" else row.get(field)
			if operator == "=" and value != expected:
				return False
			if operator == "in" and value not in expected:
				return False
			if operator == "not in" and (value or "") in expected:
				return False
			if operator == "is" and expected == "set" and not value:
				return False
		return True

	def get_all(self, doctype, filters=None, pluck=None):
		self.test.assertEqual(pluck, "name")
		rows = self.records.get(doctype, {})
		normalized = [(field, operator, value) for _doctype, field, operator, value in filters or []]
		return sorted(name for name, row in rows.items() if self._matches(row, name, normalized))

	def set_value(self, doctype, filters, field, value=None, *, update_modified):
		# Press document events must not run and the fixture stamp must stay as imported.
		self.test.assertFalse(update_modified)
		self.writes.append(doctype)
		values = field if isinstance(field, dict) else {field: value}
		rows = self.records[doctype]
		if isinstance(filters, str):
			names = [filters]
		else:
			operator, names = filters["name"]
			self.test.assertEqual(operator, "in")
			extra = [(key, "=", expected) for key, expected in filters.items() if key != "name"]
			names = [name for name in names if name in rows and self._matches(rows[name], name, extra)]
		for name in names:
			rows[name].update(values)


def press_fixture(count=686):
	return [{"name": f"fc-plan-{index}", "enabled": 1} for index in range(count)]


class FixtureCleanupTest(unittest.TestCase):
	def setUp(self):
		fixture_path = os.environ.get("PRESS_SITE_PLAN_FIXTURE")
		if fixture_path:
			self.fixtures = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
		else:
			self.fixtures = press_fixture()
		self.fixture_names = {row["name"] for row in self.fixtures}
		self.assertEqual(len(self.fixture_names), 686)

		self.records = {
			"Site Plan": {name: {"enabled": 1} for name in self.fixture_names} | {"local-plan": {"enabled": 1}},
			"Scheduled Job Type": {
				SIGNUP_METHOD: {"method": SIGNUP_METHOD, "stopped": 0},
				"press.other_job": {"method": "press.other_job", "stopped": 0},
			},
			"Team Tier": {
				tier: {"amount": 100.0, "last_invoice_amount": 0.0, "paying_user_since": 0} for tier in PRESS_TIERS
			},
			"Cluster": {"used": {"public": 1}, "unused": {"public": 1}},
			"Server Plan": {
				"used-plan": {"cluster": "used", "enabled": 1},
				"unused-plan": {"cluster": "unused", "enabled": 1},
				"no-cluster-plan": {"cluster": "", "enabled": 1},
			},
			"Cloud Region": {"used-region": {}, "unused-region": {}},
		}
		self.conf = {}
		self.db = FakeDatabase(self, self.records)

		directory = tempfile.TemporaryDirectory()
		self.addCleanup(directory.cleanup)
		fixture = Path(directory.name) / "site_plan.json"
		fixture.write_text(json.dumps(self.fixtures), encoding="utf-8")

		def get_app_path(*parts):
			self.assertEqual(parts, ("press", "fixtures", "site_plan.json"))
			return str(fixture)

		frappe = ModuleType("frappe")
		frappe.get_app_path = get_app_path
		frappe.db = self.db
		self.db.exists = lambda doctype, name: name in self.records.get(doctype, {})
		frappe.get_all = self.db.get_all
		frappe.conf = SimpleNamespace(get=self.conf.get)
		frappe.throw = self.fail_with
		frappe._ = lambda text: text
		for patcher in (
			patch.object(sys, "path", [str(APP_ROOT), *sys.path]),
			patch.dict(sys.modules, {"frappe": frappe}),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		for name in ("press_tr.hooks", "press_tr.fixture_cleanup"):
			sys.modules.pop(name, None)
		self.hooks = importlib.import_module("press_tr.hooks")
		module, _separator, function = CLEANUP_ENTRY.rpartition(".")
		self.cleanup = getattr(importlib.import_module(module), function)

	def fail_with(self, message, *args, **kwargs):
		raise ValueError(message)

	def plans(self):
		return {name: row["enabled"] for name, row in self.records["Site Plan"].items()}

	def test_after_migrate_is_a_list_with_one_cleanup_entry(self):
		self.assertIsInstance(self.hooks.after_migrate, list)
		self.assertEqual(self.hooks.after_migrate.count(CLEANUP_ENTRY), 1)

	def test_migration_disables_press_fixtures_and_old_signup_job(self):
		for _attempt in range(2):
			self.cleanup()
			self.assertEqual(self.plans(), dict.fromkeys(self.fixture_names, 0) | {"local-plan": 1})
			jobs = {name: row["stopped"] for name, row in self.records["Scheduled Job Type"].items()}
			self.assertEqual(jobs, {SIGNUP_METHOD: 1, "press.other_job": 0})

	def test_our_plan_stays_enabled_after_migrate(self):
		self.records["Site Plan"]["our-growth-plan"] = {"enabled": 1}
		self.cleanup()
		self.assertEqual(self.records["Site Plan"]["our-growth-plan"]["enabled"], 1)
		self.assertEqual(self.records["Site Plan"]["local-plan"]["enabled"], 1)

	def test_fixture_with_new_modified_stamp_is_closed_again(self):
		self.cleanup()
		# The next migrate imports the fixture again with a newer stamp and enables every plan.
		for name in self.fixture_names:
			self.records["Site Plan"][name].update(enabled=1, modified="2027-01-01 00:00:00")
		self.cleanup()
		self.assertTrue(all(self.records["Site Plan"][name]["enabled"] == 0 for name in self.fixture_names))
		self.assertEqual(self.records["Site Plan"]["local-plan"]["enabled"], 1)

	def test_team_tiers_match_our_table(self):
		table = {
			tier: {"amount": 1000.0 + index, "last_invoice_amount": 10.0 * index, "paying_user_since": index}
			for index, tier in enumerate(PRESS_TIERS)
		}
		self.conf["press_tr_team_tiers"] = table
		for _attempt in range(2):
			self.cleanup()
			self.assertEqual(self.records["Team Tier"], table)

	def test_team_tiers_stay_unchanged_without_an_approved_table(self):
		before = json.loads(json.dumps(self.records["Team Tier"]))
		self.cleanup()
		self.assertEqual(self.records["Team Tier"], before)
		self.assertNotIn("Team Tier", self.db.writes)

	def test_incomplete_team_tier_table_is_rejected_before_any_tier_changes(self):
		before = json.loads(json.dumps(self.records["Team Tier"]))
		self.conf["press_tr_team_tiers"] = {"Beginner": {"amount": 1.0, "last_invoice_amount": 0.0}}
		with self.assertRaises(ValueError):
			self.cleanup()
		self.assertEqual(self.records["Team Tier"], before)

	def test_unused_server_plan_and_cluster_are_closed(self):
		self.conf["press_tr_enabled_clusters"] = ["used"]
		for _attempt in range(2):
			self.cleanup()
			plans = {name: row["enabled"] for name, row in self.records["Server Plan"].items()}
			self.assertEqual(plans, {"used-plan": 1, "unused-plan": 0, "no-cluster-plan": 1})
			clusters = {name: row["public"] for name, row in self.records["Cluster"].items()}
			self.assertEqual(clusters, {"used": 1, "unused": 0})
		# Cloud Region has no enabled field; the record is kept and never written.
		self.assertEqual(set(self.records["Cloud Region"]), {"used-region", "unused-region"})
		self.assertNotIn("Cloud Region", self.db.writes)

	def test_unknown_cluster_name_is_rejected_before_any_cluster_changes(self):
		# A typo would match every Cluster with "not in" and close them all.
		self.conf["press_tr_enabled_clusters"] = ["used", "typo-cluster"]
		with self.assertRaises(ValueError):
			self.cleanup()
		self.assertTrue(all(row["public"] == 1 for row in self.records["Cluster"].values()))
		self.assertTrue(all(row["enabled"] == 1 for row in self.records["Server Plan"].values()))

	def test_paying_user_since_must_be_a_whole_number(self):
		table = {
			tier: {"amount": 1.0, "last_invoice_amount": 0.0, "paying_user_since": 1} for tier in PRESS_TIERS
		}
		table["Growth"]["paying_user_since"] = 1.5
		self.conf["press_tr_team_tiers"] = table
		with self.assertRaises(ValueError):
			self.cleanup()
		self.assertNotIn("Team Tier", self.db.writes)

	def test_server_plans_and_clusters_stay_unchanged_without_a_region_list(self):
		self.cleanup()
		self.assertTrue(all(row["enabled"] == 1 for row in self.records["Server Plan"].values()))
		self.assertTrue(all(row["public"] == 1 for row in self.records["Cluster"].values()))


if __name__ == "__main__":
	unittest.main()
