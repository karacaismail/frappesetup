"""The usage records a preview chose are the ones a delete removes (contract, section 10).

`purge_usage_logs(*, dry_run, names)`: the counting call returns the names it would delete. The
delete call gets exactly those names back. The gateway deletes all of them or none. If it
refuses, nothing of this layer is deleted either, and the answer does not claim a delete.
The gateway is replaced here by a function with the contract's shape. The test with real
records is `platform_core/tests/test_ai_retention_entries.py`.
"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, YzTestCase


class Gateway:
	"""A stand-in with the contract's signature. It records every call."""

	def __init__(self, names: list[str], *, waiting: int | None = None, fail_delete: Exception | None = None):
		self.names, self.waiting, self.fail_delete = list(names), waiting, fail_delete
		self.calls: list[tuple[bool, list[str] | None]] = []

	def __call__(self, *, dry_run: bool = False, names: list[str] | None = None) -> dict:
		self.calls.append((dry_run, None if names is None else list(names)))
		eligible = len(self.names) if self.waiting is None else self.waiting
		if dry_run:
			return {"eligible": eligible, "deleted": 0, "names": list(self.names)}
		if self.fail_delete is not None:
			raise self.fail_delete
		return {"eligible": eligible, "deleted": len(names or []), "names": list(names or [])}

	@property
	def deletes(self) -> list[list[str] | None]:
		return [names for dry_run, names in self.calls if not dry_run]


def installed(gateway):
	from platform_core.model_gecidi import api

	return patch.object(api, "purge_usage_logs", gateway, create=True)


class TestUsageSelection(YzTestCase):
	def old_proposal(self, client) -> str:
		name = self.make_record(MANAGER)
		arguments = {"doctype": DOCTYPE, "name": name, "data": {"title": "New"}}
		proposal_id = self.call_tool(client, "update_document", arguments)["structuredContent"]["proposal_id"]
		values = {"status": "rejected", "decided_at": add_days(now_datetime(), -31)}
		frappe.db.set_value("AI Action Proposal", proposal_id, values, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		return proposal_id

	def exists(self, name: str) -> bool:
		frappe.db.rollback()
		return bool(frappe.db.exists("AI Action Proposal", name))

	def post(self, client, **body):
		return self.human(client, "POST", "purge_logs", body=body)

	def test_web_delete_hands_the_previewed_names_to_the_gateway(self):
		manager = self.login(MANAGER)
		gateway = Gateway(["u-1", "u-2"], waiting=3)

		with installed(gateway):
			preview = self.post(manager).json["message"]
			done = self.post(manager, dry_run=False, confirmation_token=preview["confirmation_token"])

		self.assertEqual(preview["usage_logs"], {"status": "ok", "eligible": 3, "to_delete": 2, "deleted": 0})
		self.assertNotIn("u-1", str(preview))
		self.assertEqual(gateway.deletes, [["u-1", "u-2"]])
		self.assertEqual(
			done.json["message"]["usage_logs"], {"status": "ok", "eligible": 3, "to_delete": 2, "deleted": 2}
		)

	def test_other_names_at_confirmation_need_a_new_preview(self):
		"""Same numbers, other records: the human did not see these."""
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)
		gateway = Gateway(["u-1", "u-2"])

		with installed(gateway):
			token = self.post(manager).json["message"]["confirmation_token"]
			gateway.names = ["u-1", "u-3"]
			late = self.post(manager, dry_run=False, confirmation_token=token)

		self.assertEqual(late.status_code, 417)
		self.assertEqual(gateway.deletes, [])
		self.assertTrue(self.exists(old))

	def test_gateway_refusal_at_delete_leaves_everything_and_claims_no_delete(self):
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)
		gateway = Gateway(["u-1"], fail_delete=frappe.ValidationError("a usage record changed"))

		with installed(gateway):
			token = self.post(manager).json["message"]["confirmation_token"]
			done = self.post(manager, dry_run=False, confirmation_token=token)

		self.assertEqual(done.status_code, 417)
		self.assertNotIn("deleted", done.get_data(as_text=True).split("exception")[0])
		self.assertEqual(gateway.deletes, [["u-1"]])
		# All or nothing: the layer's own record is still there.
		self.assertTrue(self.exists(old))
		self.assertEqual(self.last_log(tool="purge_logs", decision="denied").deny_reason, "preview_required")

	def test_approved_tool_does_not_succeed_when_the_gateway_refuses(self):
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)
		gateway = Gateway(["u-1"], fail_delete=frappe.ValidationError("a usage record changed"))

		with installed(gateway):
			proposal = self.call_tool(manager, "purge_action_log", {})["structuredContent"]
			outcome = self.approve(manager, proposal["proposal_id"]).json["message"]

		self.assertFalse(outcome["executed"], outcome)
		self.assertNotEqual(outcome["proposal"]["result"], "succeeded")
		self.assertEqual(gateway.deletes, [["u-1"]])
		self.assertTrue(self.exists(old))
		self.human(
			manager,
			"POST",
			"resolve_proposal",
			body={"proposal_id": proposal["proposal_id"], "outcome": "failed"},
		)

	def test_approved_tool_hands_the_previewed_names_to_the_gateway(self):
		manager = self.login(MANAGER)
		gateway = Gateway(["u-1", "u-2"])

		with installed(gateway):
			proposal = self.call_tool(manager, "purge_action_log", {})["structuredContent"]
			outcome = self.approve(manager, proposal["proposal_id"]).json["message"]
		with installed(Gateway(["u-1", "u-2"])) as moved:
			second = self.call_tool(manager, "purge_action_log", {})["structuredContent"]
			moved.names = ["u-9", "u-2"]
			changed = self.approve(manager, second["proposal_id"]).json["message"]

		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual(gateway.deletes, [["u-1", "u-2"]])
		self.assertEqual((changed["executed"], changed["deny_reason"]), (False, "document_changed"))
		self.assertEqual(moved.deletes, [])

	def test_gateway_without_the_names_argument_is_never_asked_to_delete(self):
		"""An older gateway would choose its own records at delete time. It is not called."""
		manager = self.login(MANAGER)
		calls = []

		def outdated(*, dry_run=False):
			calls.append(dry_run)
			return {"eligible": 1, "deleted": 0 if dry_run else 1}

		with installed(outdated):
			preview = self.post(manager).json["message"]
			done = self.post(manager, dry_run=False, confirmation_token=preview["confirmation_token"])

		expected = {"status": "not_run", "reason": "gateway_purge_outdated"}
		self.assertEqual((preview["usage_logs"], done.json["message"]["usage_logs"]), (expected, expected))
		self.assertNotIn(False, calls)

	def test_command_line_deletes_the_names_it_chose_in_the_same_call(self):
		from platform_core.yapay_zeka import retention

		gateway = Gateway(["u-1"])
		frappe.set_user(MANAGER)

		with installed(gateway):
			result = retention.purge(365, dry_run=False)

		self.assertEqual(gateway.calls, [(True, None), (False, ["u-1"])])
		self.assertEqual(result["usage_logs"], {"status": "ok", "eligible": 1, "to_delete": 1, "deleted": 1})
