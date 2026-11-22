"""Retention periods of the layer's records (project record, personal data section).

- "AI Action Log": 365 days.
- "AI Usage Log": 365 days. Budget and invoice checks need that long.
- "AI Action Proposal": 30 days after the decision or the expiry, whichever comes first.

Every proposal has an expiry, so none stays forever. That includes a proposal with an unknown result.
The usage log belongs to the model gateway. The delete command starts the gateway's own command for it.
"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, YzTestCase


def ago(days: int):
	return add_days(now_datetime(), -days)


class TestRetentionPeriods(YzTestCase):
	def proposal(self, client, **values) -> str:
		name = self.make_record(MANAGER)
		arguments = {"doctype": DOCTYPE, "name": name, "data": {"title": "New"}}
		result = self.call_tool(client, "update_document", arguments)
		proposal_id = result["structuredContent"]["proposal_id"]
		if values:
			frappe.db.set_value("AI Action Proposal", proposal_id, values, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		return proposal_id

	def count_only(self, client) -> dict:
		return self.human(client, "POST", "purge_logs", body={}).json["message"]

	def purge(self, client, **body) -> dict:
		response = self.human(client, "POST", "purge_logs", body={"dry_run": False, **body})
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["message"]

	def exists(self, name: str) -> bool:
		frappe.db.rollback()
		return bool(frappe.db.exists("AI Action Proposal", name))

	def test_decided_proposal_goes_30_days_after_the_decision(self):
		manager = self.login(MANAGER)
		old = self.proposal(manager, status="rejected", decided_at=ago(31))
		recent = self.proposal(manager, status="rejected", decided_at=ago(29), creation=ago(400))
		done = self.proposal(manager, status="consumed", result="succeeded", decided_at=ago(31))

		result = self.purge(manager)

		self.assertFalse(self.exists(old))
		self.assertFalse(self.exists(done))
		self.assertTrue(self.exists(recent))
		self.assertEqual(result["proposal_days"], 30)

	def test_undecided_proposal_goes_30_days_after_its_expiry(self):
		manager = self.login(MANAGER)
		expired_long_ago = self.proposal(manager, expires_at=ago(31))
		expired_lately = self.proposal(manager, expires_at=ago(29), creation=ago(400))
		waiting = self.proposal(manager)

		self.purge(manager)

		self.assertFalse(self.exists(expired_long_ago))
		self.assertTrue(self.exists(expired_lately))
		self.assertTrue(self.exists(waiting))

	def test_proposal_with_an_unknown_result_goes_too(self):
		manager = self.login(MANAGER)
		unknown = {"status": "consumed", "result": "unknown"}
		old = self.proposal(manager, **unknown, decided_at=ago(31), expires_at=ago(31))
		recent = self.proposal(manager, **unknown, decided_at=ago(2), expires_at=ago(2))

		self.purge(manager)

		self.assertFalse(self.exists(old))
		self.assertTrue(self.exists(recent))

	def test_period_starts_at_the_earlier_of_decision_and_expiry(self):
		"""A proposal a human closed late still goes 30 days after its expiry."""
		manager = self.login(MANAGER)
		closed_late = self.proposal(
			manager, status="consumed", result="failed", decided_at=ago(1), expires_at=ago(31)
		)

		self.purge(manager)

		self.assertFalse(self.exists(closed_late))

	def test_counting_mode_counts_what_the_delete_removes(self):
		manager = self.login(MANAGER)
		self.proposal(manager, status="rejected", decided_at=ago(31))
		self.proposal(manager, expires_at=ago(31))
		self.proposal(manager, status="rejected", decided_at=ago(31), expires_at=ago(31))

		dry = self.count_only(manager)
		real = self.purge(manager)
		after = self.count_only(manager)

		self.assertTrue(dry["dry_run"])
		self.assertGreaterEqual(dry["proposals"], 3)
		self.assertEqual(real["proposals"], dry["proposals"])
		self.assertEqual(after["proposals"], 0)

	def test_a_longer_log_period_does_not_keep_proposals_longer(self):
		manager = self.login(MANAGER)
		old = self.proposal(manager, status="rejected", decided_at=ago(31))

		self.purge(manager, older_than_days=800)

		self.assertFalse(self.exists(old))

	def test_usage_log_period_is_applied_by_the_gateways_own_command(self):
		from platform_core.api import model

		manager = self.login(MANAGER)
		calls = []

		def fake(dry_run=True):
			calls.append(dry_run)
			return {"eligible": 7, "deleted": 0 if dry_run else 7, "dry_run": dry_run}

		with patch.object(model, "purge_usage", fake):
			dry = self.count_only(manager)
			real = self.purge(manager)

		self.assertEqual(calls, [True, False])
		self.assertEqual((dry["usage_logs"], real["usage_logs"]), (7, 7))

	def test_usage_log_command_runs_for_a_system_manager(self):
		manager = self.login(MANAGER)

		result = self.purge(manager)

		self.assertIsInstance(result["usage_logs"], int)

	def test_result_follows_the_contract(self):
		manager = self.login(MANAGER)

		result = self.count_only(manager)

		self.assertEqual(
			sorted(result), ["dry_run", "logs", "older_than_days", "proposal_days", "proposals", "usage_logs"]
		)

	def test_delete_leaves_no_copy_behind(self):
		"""Decision O-32: a retention delete is permanent. No "Deleted Document" copy is kept."""
		manager = self.login(MANAGER)
		proposal = self.proposal(manager, status="rejected", decided_at=ago(31))
		log = frappe.get_all("AI Action Log", filters={"proposal": proposal}, pluck="name")[0]
		frappe.db.set_value("AI Action Log", log, "creation", ago(400), update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		calls = []
		original = frappe.delete_doc

		def spy(doctype, name, *args, **kwargs):
			calls.append((doctype, name, kwargs.get("delete_permanently")))
			return original(doctype, name, *args, **kwargs)

		with patch.object(frappe, "delete_doc", spy):
			self.purge(manager)

		frappe.db.rollback()
		self.assertIn(("AI Action Proposal", proposal, True), calls)
		self.assertIn(("AI Action Log", log, True), calls)
		self.assertFalse(frappe.db.exists("AI Action Proposal", proposal))
		self.assertFalse(frappe.db.exists("AI Action Log", log))
		copies = frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": ("in", ["AI Action Log", "AI Action Proposal"])},
			pluck="deleted_name",
		)
		self.assertEqual(copies, [])

	def test_a_log_row_still_cannot_be_deleted_outside_the_retention_command(self):
		manager = self.login(MANAGER)
		self.call_tool(manager, "search_doctypes", {})
		log = self.last_log(tool="search_doctypes").name

		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("AI Action Log", log, force=True, delete_permanently=True)
