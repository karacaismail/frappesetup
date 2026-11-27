"""The three ways into the retention delete clean real records of both modules together.

The AI access layer owns the action log and the proposals. The model gateway owns the usage log
and cleans it with `platform_core.model_gateway.api.purge_usage_logs` (contract, section 10).
This test belongs to neither module: it writes usage records as test data and then enters
through the web endpoint, the command line function and the approved AI tool.
"""

from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.utils import add_days, now_datetime

from platform_core.ai import retention
from platform_core.ai.tests.base import DESK_USER, MANAGER, SECOND_MANAGER, USER_A, AiTestCase

USAGE_LOG = "PLT AI Usage Log"
# Names of the usage records this test made. Only these are cleaned up.
MADE: list[str] = []


def usage_record(days: int, result: str = "success") -> str:
	"""A settled usage record that was attempted `days` ago. The links point at made-up names."""
	doc = frappe.get_doc(
		{
			"doctype": USAGE_LOG,
			"attempted_at": add_days(now_datetime(), -days),
			"user": "Administrator",
			# The link columns hold UUIDs. These point at nothing.
			"provider": str(uuid4()),
			"account": str(uuid4()),
			"api": str(uuid4()),
			"model": str(uuid4()),
			"duration_ms": 1,
			"cost_known": 1,
			"result": result,
		}
	)
	doc.db_insert()
	MADE.append(doc.name)
	return doc.name


class TestRetentionEntries(AiTestCase):
	def setUp(self):
		super().setUp()
		self.clean()
		self.addCleanup(self.clean)

	def clean(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		if MADE:
			frappe.db.delete(USAGE_LOG, {"name": ("in", MADE)})
			MADE.clear()
		frappe.db.delete("Deleted Document", {"deleted_doctype": USAGE_LOG})
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

	def need_gateway_with_names(self) -> None:
		"""The delete goes through the gateway only if its function takes the chosen names (contract, section 10)."""
		import inspect

		from platform_core.model_gateway import api

		if "names" not in inspect.signature(api.purge_usage_logs).parameters:
			self.skipTest("The model gateway on this branch does not take `names` yet.")

	def records(self, *, deleted_by_gateway: bool = True) -> tuple[str, str]:
		if deleted_by_gateway:
			self.need_gateway_with_names()
		young, old = usage_record(364), usage_record(366)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		return young, old

	def exists(self, name: str) -> bool:
		frappe.db.rollback()
		return bool(frappe.db.exists(USAGE_LOG, name))

	def assert_only_the_old_one_went(self, young: str, old: str) -> None:
		self.assertTrue(self.exists(young))
		self.assertFalse(self.exists(old))
		# Decision O-32: no copy of a deleted record is kept.
		self.assertEqual(frappe.db.count("Deleted Document", {"deleted_doctype": USAGE_LOG}), 0)

	def test_web_endpoint_deletes_the_record_past_365_days(self):
		young, old = self.records()
		manager = self.login(MANAGER)

		preview = self.human(manager, "POST", "purge_logs", body={}).json["message"]
		untouched = self.exists(old)
		done = self.confirmed_purge(manager).json["message"]

		self.assertEqual(preview["usage_logs"], {"status": "ok", "eligible": 1, "to_delete": 1, "deleted": 0})
		self.assertTrue(untouched)
		self.assertEqual(done["usage_logs"]["deleted"], 1)
		self.assert_only_the_old_one_went(young, old)

	def test_command_line_function_deletes_the_record_past_365_days(self):
		"""The command line has no request and no session cookie."""
		young, old = self.records()
		frappe.set_user(MANAGER)

		counted = retention.purge()
		untouched = self.exists(old)
		frappe.set_user(MANAGER)
		done = retention.purge(365, dry_run=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- the bench command commits when it ends

		self.assertEqual(counted["usage_logs"], {"status": "ok", "eligible": 1, "to_delete": 1, "deleted": 0})
		self.assertTrue(untouched)
		self.assertEqual(done["usage_logs"]["deleted"], 1)
		self.assert_only_the_old_one_went(young, old)

	def test_approved_ai_tool_deletes_the_record_past_365_days(self):
		young, old = self.records()
		manager = self.login(MANAGER)

		result = self.call_tool(manager, "plt_purge_action_log", {})
		proposal = result["structuredContent"]
		untouched = self.exists(old)
		digest = self.digest_of(manager, proposal["proposal_id"])
		first = self.approve(manager, proposal["proposal_id"], digest)
		self.assertEqual(first.status_code, 200, "First retention approval failed")

		self.assertEqual(proposal["preview"]["details"]["usage_logs"]["to_delete"], 1)
		self.assertTrue(untouched)
		self.assertEqual(proposal["risk_level"], "R3")
		self.assertFalse(first.json["message"]["executed"])
		self.assertEqual(first.json["message"]["proposal"]["status"], "awaiting_second_approval")
		self.assertTrue(self.exists(old), "The old record must remain until the second approval")
		self.assertTrue(self.exists(young), "The young record must remain after the first approval")

		second = self.approve(self.login(SECOND_MANAGER), proposal["proposal_id"], digest)
		self.assertEqual(second.status_code, 200, "Second retention approval failed")
		outcome = second.json["message"]
		self.assertTrue(outcome["executed"], "Retention was not executed after the second approval")
		self.assertEqual(outcome["proposal"]["second_approver"], SECOND_MANAGER)
		self.assert_only_the_old_one_went(young, old)

	def test_callers_without_the_role_delete_nothing(self):
		young, old = self.records(deleted_by_gateway=False)
		desk, end_user = self.login(DESK_USER), self.login(USER_A)

		web = [self.human(client, "POST", "purge_logs", body={}).status_code for client in (desk, end_user)]
		forced = self.human(desk, "POST", "purge_logs", body={"dry_run": False, "confirmation_token": "x"})
		tool = self.call_tool(desk, "plt_purge_action_log", {})
		frappe.set_user(DESK_USER)
		with self.assertRaises(frappe.PermissionError):
			retention.purge(365, dry_run=False)
		frappe.set_user("Administrator")

		self.assertEqual(web, [403, 403])
		self.assertEqual(forced.status_code, 403)
		self.assertTrue(tool["isError"], tool)
		self.assertTrue(self.exists(young))
		self.assertTrue(self.exists(old))

	def test_gateway_itself_refuses_a_caller_without_the_role(self):
		"""The shared function checks the role itself, also when the layer's own check is skipped."""
		young, old = self.records()
		frappe.set_user(DESK_USER)

		with patch.object(frappe, "only_for", lambda *args, **kwargs: None):
			result = retention.purge(365, dry_run=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- the bench command commits when it ends
		frappe.set_user("Administrator")

		self.assertEqual(result["usage_logs"], {"status": "error", "reason": "PermissionError"})
		self.assertTrue(self.exists(young))
		self.assertTrue(self.exists(old))

	def test_one_run_takes_500_of_501_records(self):
		self.need_gateway_with_names()
		for _iteration in range(501):
			usage_record(366)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		manager = self.login(MANAGER)

		preview = self.human(manager, "POST", "purge_logs", body={}).json["message"]
		done = self.confirmed_purge(manager).json["message"]
		frappe.db.rollback()
		left = frappe.db.count(USAGE_LOG, {"name": ("in", MADE)})

		self.assertEqual(
			preview["usage_logs"], {"status": "ok", "eligible": 501, "to_delete": 500, "deleted": 0}
		)
		self.assertEqual(
			done["usage_logs"], {"status": "ok", "eligible": 501, "to_delete": 500, "deleted": 500}
		)
		self.assertEqual(left, 1)

	def test_unsettled_old_record_stays(self):
		"""The gateway keeps an attempt whose cost is not settled yet, however old it is."""
		self.need_gateway_with_names()
		pending = usage_record(400, result="pending")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		manager = self.login(MANAGER)

		self.confirmed_purge(manager)

		self.assertTrue(self.exists(pending))

	def test_old_confirmation_is_refused_when_one_more_usage_record_waits(self):
		"""Over the batch limit the number to delete stays 500, but the human saw 501 waiting."""
		self.need_gateway_with_names()
		for _iteration in range(501):
			usage_record(366)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		manager = self.login(MANAGER)

		token = self.human(manager, "POST", "purge_logs", body={}).json["message"]["confirmation_token"]
		usage_record(366)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		late = self.human(manager, "POST", "purge_logs", body={"dry_run": False, "confirmation_token": token})

		frappe.db.rollback()
		self.assertEqual(late.status_code, 417)
		self.assertEqual(frappe.db.count(USAGE_LOG, {"name": ("in", MADE)}), 502)
