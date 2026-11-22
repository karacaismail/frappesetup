"""The web endpoint deletes only what a human saw in a preview and then confirmed, once.

Contract, section 10: a destructive action needs a preview and a human approval. On the web
endpoint the counting call is the preview. It returns a single-use confirmation token. The
delete call must carry that token. Without it nothing is deleted.
"""

import time
from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, YzTestCase
from platform_core.yapay_zeka.tests.test_usage_selection import Gateway


def ago(days: int):
	return add_days(now_datetime(), -days)


class TestPurgeConfirmation(YzTestCase):
	def old_proposal(self, client) -> str:
		name = self.make_record(MANAGER)
		arguments = {"doctype": DOCTYPE, "name": name, "data": {"title": "New"}}
		proposal_id = self.call_tool(client, "update_document", arguments)["structuredContent"]["proposal_id"]
		values = {"status": "rejected", "decided_at": ago(31)}
		frappe.db.set_value("AI Action Proposal", proposal_id, values, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		return proposal_id

	def exists(self, name: str) -> bool:
		frappe.db.rollback()
		return bool(frappe.db.exists("AI Action Proposal", name))

	def post(self, client, **body):
		return self.human(client, "POST", "purge_logs", body=body)

	def test_delete_without_a_preview_is_refused_and_records_stay(self):
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)

		bare = self.post(manager, dry_run=False)
		made_up = self.post(manager, dry_run=False, confirmation_token="made-up-token")

		self.assertEqual((bare.status_code, made_up.status_code), (417, 417))
		self.assertTrue(self.exists(old))
		log = self.last_log(tool="purge_logs", decision="denied")
		self.assertEqual(log.deny_reason, "preview_required")

	def test_confirmed_delete_runs_once(self):
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)

		preview = self.post(manager).json["message"]
		kept = self.exists(old)
		first = self.post(manager, dry_run=False, confirmation_token=preview["confirmation_token"])
		again = self.post(manager, dry_run=False, confirmation_token=preview["confirmation_token"])

		self.assertTrue(preview["dry_run"])
		self.assertTrue(kept)
		self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
		self.assertFalse(first.json["message"]["dry_run"])
		self.assertNotIn("confirmation_token", first.json["message"])
		self.assertFalse(self.exists(old))
		self.assertEqual(again.status_code, 417)

	def test_token_is_bound_to_the_user_the_period_and_the_previewed_counts(self):
		from platform_core.yapay_zeka.tests.base import DESK_USER

		manager = self.login(MANAGER)
		old = self.old_proposal(manager)
		frappe.get_doc("User", DESK_USER).add_roles("System Manager")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		self.addCleanup(lambda: frappe.get_doc("User", DESK_USER).remove_roles("System Manager"))
		other = self.login(DESK_USER)

		token = self.post(manager).json["message"]["confirmation_token"]
		by_other = self.post(other, dry_run=False, confirmation_token=token)
		token = self.post(manager).json["message"]["confirmation_token"]
		other_period = self.post(manager, dry_run=False, older_than_days=800, confirmation_token=token)
		token = self.post(manager).json["message"]["confirmation_token"]
		self.old_proposal(manager)
		counts_moved = self.post(manager, dry_run=False, confirmation_token=token)

		self.assertEqual(
			(by_other.status_code, other_period.status_code, counts_moved.status_code), (417, 417, 417)
		)
		self.assertTrue(self.exists(old))

	def test_token_expires(self):
		from platform_core.yapay_zeka import retention

		manager = self.login(MANAGER)
		old = self.old_proposal(manager)

		with patch.object(retention, "CONFIRMATION_SECONDS", 1):
			token = self.post(manager).json["message"]["confirmation_token"]
			time.sleep(2)
			late = self.post(manager, dry_run=False, confirmation_token=token)

		self.assertEqual(late.status_code, 417)
		self.assertTrue(self.exists(old))

	def test_preview_says_how_many_usage_records_this_run_deletes(self):
		"""`eligible` is what waits. `to_delete` is what this run takes. `deleted` is what it took."""
		from platform_core.model_gecidi import api

		manager = self.login(MANAGER)

		gateway = Gateway([f"u-{index}" for index in range(500)], waiting=501)
		with patch.object(api, "purge_usage_logs", gateway, create=True):
			preview = self.post(manager).json["message"]
			real = self.post(manager, dry_run=False, confirmation_token=preview["confirmation_token"]).json[
				"message"
			]
			tool = self.call_tool(manager, "purge_action_log", {})["structuredContent"]["preview"]

		self.assertEqual(
			preview["usage_logs"], {"status": "ok", "eligible": 501, "to_delete": 500, "deleted": 0}
		)
		self.assertEqual(
			real["usage_logs"], {"status": "ok", "eligible": 501, "to_delete": 500, "deleted": 500}
		)
		self.assertEqual(tool["details"]["usage_logs"]["to_delete"], 500)

	def test_small_backlog_is_deleted_whole(self):
		from platform_core.model_gecidi import api

		manager = self.login(MANAGER)

		gateway = Gateway([f"u-{index}" for index in range(7)])
		with patch.object(api, "purge_usage_logs", gateway, create=True):
			preview = self.post(manager).json["message"]

		self.assertEqual(preview["usage_logs"]["to_delete"], 7)

	def test_delete_takes_only_the_records_the_preview_selected(self):
		"""A record whose period ends after the confirmation was checked is not deleted with the rest.

		The clock moves on two days right after the token is claimed. A proposal decided 29 days
		ago is then past its 30 days. The human did not see it in the preview, so it stays.
		"""
		from platform_core.yapay_zeka import retention, store

		manager = self.login(MANAGER)
		seen = self.old_proposal(manager)
		almost = self.old_proposal(manager)
		frappe.db.set_value("AI Action Proposal", almost, "decided_at", ago(29), update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		token = self.post(manager).json["message"]["confirmation_token"]
		later = patch.object(store, "now_datetime", lambda: add_days(now_datetime(), 2))
		original = retention.purge
		started = []

		def time_passes_then_delete(*args, **kwargs):
			# The preview was verified a moment ago. Now the clock moves on, then the delete starts.
			if kwargs.get("dry_run") is False and not started:
				later.start()
				started.append(True)
			return original(*args, **kwargs)

		try:
			with patch.object(retention, "purge", time_passes_then_delete):
				done = self.post(manager, dry_run=False, confirmation_token=token)
		finally:
			if started:
				later.stop()

		self.assertEqual(done.status_code, 200, done.get_data(as_text=True))
		self.assertEqual(started, [True])
		self.assertFalse(self.exists(seen))
		self.assertTrue(self.exists(almost))

	def test_old_confirmation_is_refused_when_the_waiting_total_changes(self):
		"""Over the batch limit the number to delete stays the same, but more records wait than the human saw."""
		from platform_core.yapay_zeka import retention

		manager = self.login(MANAGER)
		first, second = self.old_proposal(manager), self.old_proposal(manager)

		with patch.object(retention, "BATCH_SIZE", 1):
			preview = self.post(manager).json["message"]
			third = self.old_proposal(manager)
			late = self.post(manager, dry_run=False, confirmation_token=preview["confirmation_token"])

		# Other tests may have left old proposals on the site. At least the two of this test wait.
		self.assertEqual(preview["proposals"], 1)
		self.assertGreaterEqual(preview["proposals_waiting"], 2)
		self.assertEqual(late.status_code, 417)
		for name in (first, second, third):
			self.assertTrue(self.exists(name))
		self.assertEqual(self.last_log(tool="purge_logs", decision="denied").deny_reason, "preview_required")
