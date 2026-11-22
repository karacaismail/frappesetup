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

	def gateway(self, purge):
		"""Put a purge function on the gateway's public interface for one test."""
		from platform_core.model_gecidi import api

		return patch.object(api, "purge_usage_logs", purge, create=True)

	def without_gateway_purge(self):
		from platform_core.model_gecidi import api

		return patch.object(api, "purge_usage_logs", None, create=True)

	def test_usage_log_is_cleaned_by_the_gateways_shared_function(self):
		"""Contract, section 10: `purge_usage_logs(*, dry_run)` returns `eligible` and `deleted`."""
		manager = self.login(MANAGER)
		calls = []

		def fake(*, dry_run=False):
			calls.append((dry_run, frappe.session.user))
			return {"eligible": 501, "deleted": 0 if dry_run else 500}

		with self.gateway(fake):
			dry = self.count_only(manager)
			real = self.purge(manager)

		self.assertEqual(calls, [(True, MANAGER), (False, MANAGER)])
		self.assertEqual(dry["usage_logs"], {"status": "ok", "eligible": 501, "deleted": 0})
		self.assertEqual(real["usage_logs"], {"status": "ok", "eligible": 501, "deleted": 500})

	def test_missing_gateway_function_is_reported_as_not_run(self):
		manager = self.login(MANAGER)

		with self.without_gateway_purge():
			result = self.purge(manager)

		self.assertEqual(result["usage_logs"], {"status": "not_run", "reason": "gateway_purge_unavailable"})

	def test_refusal_of_the_gateway_is_reported_as_an_error(self):
		manager = self.login(MANAGER)
		old = self.proposal(manager, status="rejected", decided_at=ago(31))

		def refuse(*, dry_run=False):
			raise frappe.PermissionError("leak-marker in a gateway error")

		with self.gateway(refuse):
			response = self.human(manager, "POST", "purge_logs", body={"dry_run": False})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.json["message"]["usage_logs"], {"status": "error", "reason": "PermissionError"}
		)
		self.assertNotIn("leak-marker", response.get_data(as_text=True))
		self.assertFalse(self.exists(old))

	def test_terminal_call_uses_the_same_function(self):
		"""The command line has no session cookie. The same shared function is called there."""
		from platform_core.yapay_zeka import retention

		calls = []

		def fake(*, dry_run=False):
			calls.append(dry_run)
			return {"eligible": 2, "deleted": 0 if dry_run else 2}

		frappe.set_user(MANAGER)
		with self.gateway(fake):
			counted = retention.purge()
			result = retention.purge(365, dry_run=False)
		with self.without_gateway_purge():
			missing = retention.purge(365, dry_run=False)

		# V-10: without `dry_run` the command only counts, and the gateway is asked to count too.
		self.assertEqual(calls, [True, False])
		self.assertEqual(counted["usage_logs"], {"status": "ok", "eligible": 2, "deleted": 0})
		self.assertEqual(result["usage_logs"], {"status": "ok", "eligible": 2, "deleted": 2})
		self.assertEqual(missing["usage_logs"]["status"], "not_run")

	def test_result_has_the_fields_the_contract_requires(self):
		import yaml

		from platform_core.yapay_zeka.tests.test_registry import APP_ROOT

		contract = APP_ROOT.parents[2] / "contracts" / "platform_core-yapay-zeka.openapi.yaml"
		if not contract.exists():
			self.skipTest(f"Contract file is missing in this environment: {contract}")
		schema = yaml.safe_load(contract.read_text())["components"]["schemas"]["PurgeResult"]
		manager = self.login(MANAGER)

		result = self.count_only(manager)

		self.assertEqual(sorted(result), sorted(schema["required"]))
		self.assertEqual(sorted(schema["properties"]), sorted(schema["required"]))
		self.assertIn(
			result["usage_logs"]["status"], schema["properties"]["usage_logs"]["properties"]["status"]["enum"]
		)

	def test_purge_preview_states_both_periods_and_the_limit_of_one_run(self):
		from platform_core.yapay_zeka import retention

		manager = self.login(MANAGER)
		for _ in range(4):
			self.proposal(manager, status="rejected", decided_at=ago(31))

		def fake(*, dry_run=False):
			return {"eligible": 501, "deleted": 0}

		with self.gateway(fake), patch.object(retention, "BATCH_SIZE", 3):
			result = self.call_tool(manager, "purge_action_log", {"older_than_days": 800})

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
		self.assertEqual(details["usage_logs"], {"status": "ok", "eligible": 501, "deleted": 0})

	def test_approved_purge_counts_again_when_it_runs(self):
		"""Records that became old after the preview stop the approval: the human saw another count."""
		manager = self.login(MANAGER)
		with self.without_gateway_purge():
			result = self.call_tool(manager, "purge_action_log", {})
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
			"Deleted Document", {"deleted_doctype": ("in", ["AI Action Log", "AI Action Proposal"])}
		)
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
