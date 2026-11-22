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

from platform_core.ai.tests.base import DOCTYPE, MANAGER, AiTestCase


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
	from platform_core.model_gateway import api

	return patch.object(api, "purge_usage_logs", gateway, create=True)


class PurgeRequests:
	"""Helpers shared by the test classes of this file."""

	def old_proposal(self, client) -> str:
		name = self.make_record(MANAGER)
		arguments = {"doctype": DOCTYPE, "name": name, "data": {"title": "New"}}
		proposal_id = self.call_tool(client, "plt_update_document", arguments)["structuredContent"]["proposal_id"]
		values = {"status": "rejected", "decided_at": add_days(now_datetime(), -31)}
		frappe.db.set_value("PLT AI Action Proposal", proposal_id, values, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		return proposal_id

	def exists(self, name: str) -> bool:
		frappe.db.rollback()
		return bool(frappe.db.exists("PLT AI Action Proposal", name))

	def post(self, client, **body):
		return self.human(client, "POST", "purge_logs", body=body)


class TestUsageSelection(PurgeRequests, AiTestCase):
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
			proposal = self.call_tool(manager, "plt_purge_action_log", {})["structuredContent"]
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
			proposal = self.call_tool(manager, "plt_purge_action_log", {})["structuredContent"]
			outcome = self.approve(manager, proposal["proposal_id"]).json["message"]
		with installed(Gateway(["u-1", "u-2"])) as moved:
			second = self.call_tool(manager, "plt_purge_action_log", {})["structuredContent"]
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
		from platform_core.ai import retention

		gateway = Gateway(["u-1"])
		frappe.set_user(MANAGER)

		with installed(gateway):
			result = retention.purge(365, dry_run=False)

		self.assertEqual(gateway.calls, [(True, None), (False, ["u-1"])])
		self.assertEqual(result["usage_logs"], {"status": "ok", "eligible": 1, "to_delete": 1, "deleted": 1})

	def test_unexpected_gateway_failure_after_a_delete_is_rolled_back_and_answered_safely(self):
		"""The gateway deletes one record and then fails with an error nobody planned for."""
		manager = self.login(MANAGER)
		old, victim = self.old_proposal(manager), self.old_proposal(manager)
		marker = "leak-marker-in-a-gateway-crash"

		class Crashing(Gateway):
			def __call__(self, *, dry_run=False, names=None):
				if not dry_run:
					self.calls.append((dry_run, list(names or [])))
					frappe.db.delete("PLT AI Action Proposal", {"name": victim})
					raise RuntimeError(marker)
				return super().__call__(dry_run=dry_run, names=names)

		gateway = Crashing(["u-1"])
		frappe.db.delete("Error Log")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		with installed(gateway):
			token = self.post(manager).json["message"]["confirmation_token"]
			done = self.post(manager, dry_run=False, confirmation_token=token)

		self.assertEqual(done.status_code, 417, done.get_data(as_text=True))
		self.assertNotIn(marker, done.get_data(as_text=True))
		self.assertEqual(gateway.deletes, [["u-1"]])
		# Rolled back: the record the gateway deleted and the layer's own record are both there.
		self.assertTrue(self.exists(victim))
		self.assertTrue(self.exists(old))
		log = self.last_log(tool="purge_logs", decision="denied")
		self.assertEqual(log.deny_reason, "purge_failed")
		stored = frappe.get_all("Error Log", fields=["method", "error"]) + frappe.get_all(
			"PLT AI Action Log", fields=["*"]
		)
		self.assertNotIn(marker, str(stored))

	def test_permission_refusal_of_the_gateway_at_delete_stays_403(self):
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)
		gateway = Gateway(["u-1"], fail_delete=frappe.PermissionError("no"))

		with installed(gateway):
			token = self.post(manager).json["message"]["confirmation_token"]
			done = self.post(manager, dry_run=False, confirmation_token=token)

		self.assertEqual(done.status_code, 403)
		self.assertTrue(self.exists(old))


# The one text a caller gets for each way a delete can stop (contract, `purge_logs`).
TEXTS = {
	403: "You do not have permission for this action.",
	"purge_failed": "The delete failed and was rolled back. Nothing was deleted.",
	"preview_required": "Ask for a preview first, then send its confirmation token. Nothing was deleted.",
}


class TestDeleteErrorAnswers(PurgeRequests, AiTestCase):
	"""Every error during a delete ends in one fixed answer, with error details shown or hidden.

	Frappe puts the traceback and the collected messages into the response for a system user
	when the site shows error details. The text of a foreign error must not be in either.
	"""

	MARKER = "leak-marker-from-a-delete-hook"

	def failing(self, error: Exception):
		marker = self.MARKER

		class Failing(Gateway):
			def __call__(self, *, dry_run=False, names=None):
				if dry_run:
					return super().__call__(dry_run=dry_run, names=names)
				# A hook collects a message with a record value, then raises with it too.
				frappe.msgprint(f"value {marker}")
				raise error

		return Failing(["u-1"])

	def delete_with(self, error: Exception, *, details: bool):
		manager = self.login(MANAGER)
		old = self.old_proposal(manager)
		with (
			installed(self.failing(error)),
			patch("frappe.utils.response.is_traceback_allowed", lambda: details),
		):
			token = self.post(manager).json["message"]["confirmation_token"]
			response = self.post(manager, dry_run=False, confirmation_token=token)
		self.assertTrue(self.exists(old))
		return response

	def assert_fixed(self, response, status: int, text: str) -> None:
		body = response.get_data(as_text=True)
		self.assertEqual(response.status_code, status, body)
		self.assertNotIn(self.MARKER, body)
		self.assertIn(text, body)
		frappe.db.rollback()
		stored = frappe.get_all("PLT AI Action Log", fields=["*"]) + frappe.get_all("Error Log", fields=["*"])
		self.assertNotIn(self.MARKER, str(stored))

	def test_permission_error_of_a_hook_becomes_the_fixed_403(self):
		for details in (True, False):
			response = self.delete_with(
				frappe.PermissionError(f"no access to {self.MARKER}"), details=details
			)
			self.assert_fixed(response, 403, TEXTS[403])

	def test_unexpected_error_becomes_the_fixed_417(self):
		for details in (True, False):
			response = self.delete_with(RuntimeError(self.MARKER), details=details)
			self.assert_fixed(response, 417, TEXTS["purge_failed"])
			self.assertEqual(self.last_log(tool="purge_logs", decision="denied").deny_reason, "purge_failed")

	def test_validation_error_becomes_the_fixed_preview_answer(self):
		for details in (True, False):
			response = self.delete_with(frappe.ValidationError(self.MARKER), details=details)
			self.assert_fixed(response, 417, TEXTS["preview_required"])

	def test_missing_token_gets_the_fixed_text_when_details_are_hidden(self):
		manager = self.login(MANAGER)

		with patch("frappe.utils.response.is_traceback_allowed", lambda: False):
			response = self.post(manager, dry_run=False)

		self.assertEqual(response.status_code, 417)
		self.assertIn(TEXTS["preview_required"], response.get_data(as_text=True))

	def test_developer_mode_error_record_gets_nothing_of_the_selection(self):
		"""In developer mode Frappe writes an error record with the values of local variables.

		The stopped delete holds the chosen record names and the manager's id in such variables.
		The fixed error tells Frappe to write no record. The same function Frappe calls for a
		failed request is called here with the error the delete raised.
		"""
		from frappe.utils.error import log_error_snapshot

		from platform_core.ai import retention

		chosen = "usage-record-name-4815"
		cases = (
			RuntimeError("crash"),
			frappe.ValidationError("changed"),
			frappe.PermissionError("no"),
		)
		for cause in cases:
			written = []

			def record(*args, **kwargs):
				# What Frappe would store: the traceback with the values of local variables.
				written.append(frappe.get_traceback(with_context=True))

			frappe.set_user(MANAGER)
			with installed(Gateway([chosen], fail_delete=cause)):
				token = retention.purge_from_web()["confirmation_token"]
				try:
					retention.purge_from_web(dry_run=False, confirmation_token=token)
				except Exception as error:
					with patch("frappe.utils.error.log_error", record):
						log_error_snapshot(error)
				else:
					self.fail("The delete did not stop.")
			frappe.set_user("Administrator")
			frappe.db.rollback()
			self.assertNotIn(chosen, str(written), type(cause).__name__)
			self.assertNotIn(MANAGER, str(written), type(cause).__name__)
			self.assertEqual(written, [], type(cause).__name__)
