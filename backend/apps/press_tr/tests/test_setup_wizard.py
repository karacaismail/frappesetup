"""G-7: press_tr starts the Agent "Complete Setup Wizard" job once per new site.

Press has ``Agent.complete_setup_wizard`` but no code calls it. press_tr calls it from the Site
``on_update`` hook when the site becomes Active. The test needs no Frappe install: ``frappe`` and
``press.agent`` are replaced with stubs.
"""

import importlib
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
HOOK = "press_tr.setup_wizard.start_setup_wizard"
JOB_TYPE = "Complete Setup Wizard"


class SetupWizardTest(unittest.TestCase):
	def setUp(self):
		self.jobs = []
		self.errors = []
		self.trials = set()
		self.values = {
			("Team", "team-1"): {"user": "owner@example.test", "country": "Turkey", "currency": "TRY"},
			("User", "owner@example.test"): {
				"full_name": "Site Owner",
				"email": "owner@example.test",
				"language": "tr",
			},
			("Account Request", "request-1"): {
				"geo_location": json.dumps({"timezone": "Europe/Istanbul"}),
			},
		}

		frappe = ModuleType("frappe")
		frappe.db = SimpleNamespace(exists=self.exists, get_value=self.get_value)
		frappe.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
		frappe.log_error = lambda title=None, **kwargs: self.errors.append(title)

		agent_module = ModuleType("press.agent")
		test = self

		class Agent:
			def __init__(self, server, server_type="Server"):
				self.server = server
				test.assertEqual(server_type, "Server")

			def complete_setup_wizard(self, site, data):
				test.jobs.append({"site": site.name, "server": self.server, "data": data})
				return SimpleNamespace(name=f"job-{len(test.jobs)}")

		agent_module.Agent = Agent
		press = ModuleType("press")
		press.agent = agent_module
		for patcher in (
			patch.object(sys, "path", [str(APP_ROOT), *sys.path]),
			patch.dict(sys.modules, {"frappe": frappe, "press": press, "press.agent": agent_module}),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		for name in ("press_tr.hooks", "press_tr.setup_wizard"):
			sys.modules.pop(name, None)
		self.hooks = importlib.import_module("press_tr.hooks")
		module, _separator, function = HOOK.rpartition(".")
		self.start = getattr(importlib.import_module(module), function)

	def exists(self, doctype, filters):
		if doctype == "Agent Job":
			self.assertEqual(filters["job_type"], JOB_TYPE)
			return any(job["site"] == filters["site"] for job in self.jobs)
		if doctype == "Product Trial Request":
			return filters["site"] in self.trials
		self.fail(f"Unexpected exists call: {doctype}")

	def get_value(self, doctype, name, fields, as_dict=False):
		self.assertTrue(as_dict)
		row = self.values.get((doctype, name))
		return SimpleNamespace(**{field: row.get(field) for field in fields}) if row else None

	def site(self, **values):
		defaults = {
			"name": "new.example.test",
			"server": "f1.example.test",
			"status": "Active",
			"setup_wizard_complete": 0,
			"standby_for": None,
			"standby_for_product": None,
			"team": "team-1",
			"account_request": "request-1",
		}
		return SimpleNamespace(**(defaults | values))

	def test_site_update_hook_is_registered_and_validate_hook_is_kept(self):
		site_events = self.hooks.doc_events["Site"]
		self.assertEqual(site_events["on_update"], HOOK)
		self.assertEqual(site_events["validate"], "press_tr.backup_keys.validate_site_keys")

	def test_new_active_site_starts_the_job_once(self):
		site = self.site()
		self.start(site, "on_update")
		self.start(site, "on_update")
		self.assertEqual(len(self.jobs), 1)
		self.assertEqual(self.jobs[0]["site"], "new.example.test")
		self.assertEqual(self.jobs[0]["server"], "f1.example.test")
		self.assertEqual(
			self.jobs[0]["data"],
			{
				"language": "tr",
				"country": "Turkey",
				"timezone": "Europe/Istanbul",
				"currency": "TRY",
				"full_name": "Site Owner",
				"email": "owner@example.test",
			},
		)

	def test_site_that_is_not_active_starts_no_job(self):
		self.start(self.site(status="Pending"), "on_update")
		self.assertEqual(self.jobs, [])

	def test_completed_wizard_starts_no_job(self):
		self.start(self.site(setup_wizard_complete=1), "on_update")
		self.assertEqual(self.jobs, [])

	def test_standby_and_product_trial_sites_are_left_to_press(self):
		self.start(self.site(standby_for="erpnext"), "on_update")
		self.start(self.site(standby_for_product="trial-product"), "on_update")
		self.trials.add("trial.example.test")
		self.start(self.site(name="trial.example.test"), "on_update")
		self.assertEqual(self.jobs, [])

	def test_missing_owner_data_starts_no_job_and_logs_the_reason(self):
		self.values[("Account Request", "request-1")] = {"geo_location": None}
		self.start(self.site(), "on_update")
		self.assertEqual(self.jobs, [])
		self.assertEqual(len(self.errors), 1)


if __name__ == "__main__":
	unittest.main()
