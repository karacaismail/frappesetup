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

from platform_core.ai.tests.base import DOCTYPE, MANAGER, AiTestCase


def ago(days: int):
	return add_days(now_datetime(), -days)


class TestRetentionPeriods(AiTestCase):
	def proposal(self, client, **values) -> str:
		name = self.make_record(MANAGER)
		arguments = {"doctype": DOCTYPE, "name": name, "data": {"title": "New"}}
		result = self.call_tool(client, "plt_update_document", arguments)
		proposal_id = result["structuredContent"]["proposal_id"]
		if values:
			frappe.db.set_value("PLT AI Action Proposal", proposal_id, values, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		return proposal_id

	def count_only(self, client) -> dict:
		return self.human(client, "POST", "purge_logs", body={}).json["message"]

	def purge(self, client, **body) -> dict:
		response = self.confirmed_purge(client, **body)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["message"]

	def exists(self, name: str) -> bool:
		frappe.db.rollback()
		return bool(frappe.db.exists("PLT AI Action Proposal", name))

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

	def without_gateway_purge(self):
		from platform_core.model_gateway import api

		return patch.object(api, "purge_usage_logs", None, create=True)

	def test_missing_gateway_function_is_reported_as_not_run(self):
		manager = self.login(MANAGER)

		with self.without_gateway_purge():
			result = self.purge(manager)

		self.assertEqual(result["usage_logs"], {"status": "not_run", "reason": "gateway_purge_unavailable"})

	def test_result_has_the_fields_the_contract_requires(self):
		import yaml

		from platform_core.ai.tests.test_registry import APP_ROOT

		contract = APP_ROOT.parents[2] / "contracts" / "platform_core-ai.openapi.yaml"
		if not contract.exists():
			self.skipTest(f"Contract file is missing in this environment: {contract}")
		schema = yaml.safe_load(contract.read_text())["components"]["schemas"]["PurgeResult"]
		manager = self.login(MANAGER)

		result = self.count_only(manager)

		# The counting mode adds the confirmation token. Every other field is required.
		self.assertEqual(sorted(set(result) - {"confirmation_token"}), sorted(schema["required"]))
		self.assertEqual(
			sorted(set(schema["properties"]) - {"confirmation_token"}), sorted(schema["required"])
		)
		self.assertIn(
			result["usage_logs"]["status"], schema["properties"]["usage_logs"]["properties"]["status"]["enum"]
		)

	def test_purge_preview_states_both_periods_and_the_limit_of_one_run(self):
		from platform_core.ai import retention

		manager = self.login(MANAGER)
		for _ in range(4):
			self.proposal(manager, status="rejected", decided_at=ago(31))

		from platform_core.ai.tests.test_usage_selection import Gateway, installed

		gateway = Gateway([f"u-{index}" for index in range(500)], waiting=501)
		with installed(gateway), patch.object(retention, "BATCH_SIZE", 3):
			result = self.call_tool(manager, "plt_purge_action_log", {"older_than_days": 800})

		preview = result["structuredContent"]["preview"]
		details = preview["details"]
		for text in ("800 days", "365 days", "30 days", "at most 3 records of each kind"):
			self.assertIn(text, preview["summary"])
		self.assertEqual(details["batch_size"], 3)
		# What one run deletes and what waits are two numbers.
		self.assertEqual(details["proposals"], 3)
		self.assertGreaterEqual(details["proposals_waiting"], 4)
		self.assertEqual(details["older_than_days"], 800)
		# For the usage log `eligible` is what waits. The gateway deletes it in batches.
		self.assertEqual(
			details["usage_logs"], {"status": "ok", "eligible": 501, "to_delete": 500, "deleted": 0}
		)

	def test_approved_purge_counts_again_when_it_runs(self):
		"""Records that became old after the preview stop the approval: the human saw another count."""
		manager = self.login(MANAGER)
		with self.without_gateway_purge():
			result = self.call_tool(manager, "plt_purge_action_log", {})
			proposal_id = result["structuredContent"]["proposal_id"]
			digest = self.digest_of(manager, proposal_id)
			self.proposal(manager, status="rejected", decided_at=ago(31))
			outcome = self.approve(manager, proposal_id, digest).json["message"]

		self.assertEqual((outcome["executed"], outcome["deny_reason"]), (False, "document_changed"))

	def test_delete_leaves_no_copy_behind(self):
		"""Decision O-32: a retention delete is permanent. No "Deleted Document" copy is kept."""
		manager = self.login(MANAGER)
		# Copies an earlier run may have left on this test site are not this run's result.
		frappe.db.delete(
			"Deleted Document", {"deleted_doctype": ("in", ["PLT AI Action Log", "PLT AI Action Proposal"])}
		)
		proposal = self.proposal(manager, status="rejected", decided_at=ago(31))
		log = frappe.get_all("PLT AI Action Log", filters={"proposal": proposal}, pluck="name")[0]
		frappe.db.set_value("PLT AI Action Log", log, "creation", ago(400), update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		calls = []
		original = frappe.delete_doc

		def spy(doctype, name, *args, **kwargs):
			calls.append((doctype, name, kwargs.get("delete_permanently")))
			return original(doctype, name, *args, **kwargs)

		with patch.object(frappe, "delete_doc", spy):
			self.purge(manager)

		frappe.db.rollback()
		self.assertIn(("PLT AI Action Proposal", proposal, True), calls)
		self.assertIn(("PLT AI Action Log", log, True), calls)
		self.assertFalse(frappe.db.exists("PLT AI Action Proposal", proposal))
		self.assertFalse(frappe.db.exists("PLT AI Action Log", log))
		copies = frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": ("in", ["PLT AI Action Log", "PLT AI Action Proposal"])},
			pluck="deleted_name",
		)
		self.assertEqual(copies, [])

	def test_a_log_row_still_cannot_be_deleted_outside_the_retention_command(self):
		manager = self.login(MANAGER)
		self.call_tool(manager, "plt_search_doctypes", {})
		log = self.last_log(tool="plt_search_doctypes").name

		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("PLT AI Action Log", log, force=True, delete_permanently=True)
