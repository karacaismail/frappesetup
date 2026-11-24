"""G-7: press_tr starts the Agent "Complete Setup Wizard" job once per new site.

Press has ``Agent.complete_setup_wizard`` but no code calls it. Press sets a new site Active with
``frappe.db.set_value``, which skips ``on_update``. Press's own five-minute check
``sync_sites_setup_wizard_complete_status`` then saves each Active site whose wizard is not done.
That save runs the press_tr ``on_update`` hook.

The Agent passes the payload to Frappe 16 ``setup_complete``. Frappe looks up ``language`` and
``lang`` by the Language name, not by the code. The test needs no Frappe install: ``frappe`` and
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
SKIP_TITLE = "press_tr setup wizard skipped"


class SetupWizardTest(unittest.TestCase):
	def setUp(self):
		self.jobs = []
		self.errors = []
		self.locks = []
		self.trials = set()
		self.values = {
			("Team", "team-1"): {
				"user": "owner@example.test",
				"country": "Turkey",
				"currency": "TRY",
				"account_request": "team-request",
			},
			("User", "owner@example.test"): {
				"full_name": "Site Owner",
				"email": "owner@example.test",
				"language": "tr",
			},
			("Language", "tr"): {"language_name": "Türkçe"},
			("Account Request", "request-1"): {
				"geo_location": json.dumps({"timezone": "Europe/Istanbul"}),
			},
			("Account Request", "team-request"): {
				"geo_location": json.dumps({"timezone": "Europe/Istanbul"}),
			},
			("Country", "Turkey"): {"time_zones": "Europe/Istanbul"},
		}

		frappe = ModuleType("frappe")
		frappe.db = SimpleNamespace(exists=self.exists, get_value=self.get_value)
		frappe.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
		frappe.log_error = self.log_error

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

	def log_error(self, title=None, message=None, reference_doctype=None, reference_name=None):
		self.errors.append({"method": title, "reference_doctype": reference_doctype, "reference_name": reference_name})

	def exists(self, doctype, filters):
		if doctype == "Agent Job":
			self.assertEqual(filters["job_type"], JOB_TYPE)
			return any(job["site"] == filters["site"] for job in self.jobs)
		if doctype == "Product Trial Request":
			return filters["site"] in self.trials
		if doctype == "Error Log":
			return any(all(error.get(key) == value for key, value in filters.items()) for error in self.errors)
		self.fail(f"Unexpected exists call: {doctype}")

	def get_value(self, doctype, name, fields, as_dict=False, for_update=False):
		if doctype == "Site":
			self.assertTrue(for_update)
			self.locks.append(name)
			return name
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
			"apps": [SimpleNamespace(app="frappe")],
		}
		return SimpleNamespace(**(defaults | values))

	def expected_payload(self):
		return {
			"language": "Türkçe",
			"lang": "Türkçe",
			"country": "Turkey",
			"timezone": "Europe/Istanbul",
			"currency": "TRY",
			"full_name": "Site Owner",
			"email": "owner@example.test",
		}

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
		self.assertEqual(self.jobs[0]["data"], self.expected_payload())
		# The site row is locked before the job check, so two saves cannot both start a job.
		self.assertIn("new.example.test", self.locks)

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

	def test_administrator_team_site_starts_no_job(self):
		self.values[("Team", "team-1")]["user"] = "Administrator"
		self.start(self.site(), "on_update")
		self.assertEqual(self.jobs, [])

	def test_site_with_an_app_that_needs_more_wizard_data_starts_no_job(self):
		# ERPNext wizard stages need company data. This payload does not have it.
		apps = [SimpleNamespace(app="frappe"), SimpleNamespace(app="erpnext")]
		self.start(self.site(apps=apps), "on_update")
		self.assertEqual(self.jobs, [])

	def test_dashboard_site_uses_the_team_account_request(self):
		self.start(self.site(account_request=None), "on_update")
		self.assertEqual(len(self.jobs), 1)
		self.assertEqual(self.jobs[0]["data"], self.expected_payload())

	def test_country_with_one_time_zone_fills_a_missing_timezone(self):
		self.values[("Account Request", "request-1")] = {"geo_location": None}
		self.values[("Account Request", "team-request")] = {"geo_location": None}
		self.start(self.site(), "on_update")
		self.assertEqual(len(self.jobs), 1)
		self.assertEqual(self.jobs[0]["data"]["timezone"], "Europe/Istanbul")

	def test_missing_owner_data_starts_no_job_and_logs_the_reason_once(self):
		self.values[("Account Request", "request-1")] = {"geo_location": None}
		self.values[("Account Request", "team-request")] = {"geo_location": None}
		self.values[("Country", "Turkey")] = {"time_zones": "Europe/Istanbul\nAsia/Nicosia"}
		site = self.site()
		self.start(site, "on_update")
		self.start(site, "on_update")
		self.assertEqual(self.jobs, [])
		self.assertEqual(len(self.errors), 1)
		self.assertEqual(self.errors[0]["method"], SKIP_TITLE)
		self.assertEqual(self.errors[0]["reference_name"], "new.example.test")

	def test_missing_language_starts_no_job(self):
		self.values[("User", "owner@example.test")]["language"] = None
		self.start(self.site(), "on_update")
		self.assertEqual(self.jobs, [])


if __name__ == "__main__":
	unittest.main()
