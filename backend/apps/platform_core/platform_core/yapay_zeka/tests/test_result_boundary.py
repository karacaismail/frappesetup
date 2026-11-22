"""Result state and denial logging rules decided after the second independent review.

B3: a result is `failed` only when the error came from the layer's own pre-check, before any
Frappe document method ran. Any error after that point is `unknown`, whatever its type.
B6: every denial with a known identity is written to the AI Action Log and survives the error response.
"""

from unittest.mock import patch

import frappe
from frappe.core.doctype.user.user import generate_keys
from frappe.utils import add_to_date, now_datetime

from platform_core.yapay_zeka.errors import ToolDenied
from platform_core.yapay_zeka.tests import sample_tools
from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, YzTestCase

HOOK = "platform_core.yapay_zeka.tests.sample_tools.external_effect_then_fail"


def with_before_save_hook():
	"""Register the failing `before_save` hook for the test DocType in every thread of this process."""
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		value = original(hook, *args, **kwargs)
		if hook == "doc_events":
			value = {**value, DOCTYPE: {"before_save": [HOOK]}}
		return value

	return patch.object(frappe, "get_hooks", get_hooks)


class TestResultBoundary(YzTestCase):
	def setUp(self):
		super().setUp()
		frappe.cache.delete_value(sample_tools.EXTERNAL_MARKER)

	def title(self, name: str) -> str:
		return frappe.db.get_value(DOCTYPE, name, "title")

	def test_error_in_a_hook_before_the_row_is_written_stays_unknown(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]
		digest = self.digest_of(client, proposal_id)

		with with_before_save_hook():
			outcome = self.approve(client, proposal_id, digest).json["message"]
		again = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "Again"}}
		)

		self.assertEqual(frappe.cache.get_value(sample_tools.EXTERNAL_MARKER), name)
		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["proposal"]["result"], "unknown")
		self.assertEqual(self.title(name), "Old")
		self.assert_denied(again, "unresolved_unknown")
		log = self.last_log(proposal=proposal_id, stage="execute")
		self.assertEqual((log.decision, log.result), ("error", "unknown"))

	def test_tool_denied_after_a_committed_write_stays_unknown(self):
		from platform_core.yapay_zeka.tools import write

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		original = write.write_update

		def writes_then_denies(prepared):
			original(prepared)
			frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
			raise ToolDenied("document_changed", "raised after the write")

		with patch.object(write, "write_update", writes_then_denies):
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertEqual(self.title(name), "New")
		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["proposal"]["result"], "unknown")

	def test_tool_denied_after_an_uncommitted_write_stays_unknown(self):
		from platform_core.yapay_zeka.tools import write

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]
		digest = self.digest_of(client, proposal_id)

		def denies(prepared):
			raise ToolDenied("document_changed", "raised inside the write step")

		with patch.object(write, "write_update", denies):
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertEqual(outcome["proposal"]["result"], "unknown")

	def test_error_in_the_layers_own_pre_check_is_failed(self):
		from platform_core.yapay_zeka.tools import write

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		original = write.prepare_update

		def rival():
			doc = frappe.get_doc(DOCTYPE, name)
			doc.title = "Rival"
			doc.save()

		def rival_then_prepare(*args, **kwargs):
			# The rival change is committed by another connection, as a real rival request would.
			self.in_other_connection(rival)
			return original(*args, **kwargs)

		with patch.object(write, "prepare_update", rival_then_prepare):
			outcome = self.approve(client, proposal_id, digest).json["message"]
		again = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "Again"}}
		)

		self.assertFalse(outcome["executed"])
		self.assertEqual(
			(outcome["proposal"]["result"], outcome["proposal"]["error"]), ("failed", "document_changed")
		)
		self.assertEqual(self.title(name), "Rival")
		self.assertFalse(again["isError"], again)

	def test_every_built_in_write_tool_separates_pre_check_from_write(self):
		from platform_core.yapay_zeka import registry

		frappe.set_user(MANAGER)
		for tool in registry.builtin_tools():
			if tool.kind == "write":
				self.assertIsNotNone(tool.prepare, tool.name)


class TestKnownIdentityDenials(YzTestCase):
	def test_api_key_denial_on_mcp_is_logged(self):
		keys = generate_keys(MANAGER)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		response = self.rpc(
			self.anonymous(),
			"tools/list",
			headers={"Authorization": f"token {keys['api_key']}:{keys['api_secret']}"},
		)

		self.assertEqual(response.status_code, 403)
		log = self.last_log(deny_reason="credential_not_accepted", user=MANAGER)
		self.assertEqual((log.decision, log.principal, log.stage), ("denied", "other", "auth"))

	def test_token_of_an_expired_session_is_logged(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		sid = client.get_cookie("sid").value
		session = frappe.cache.hget("session", sid)
		session["data"]["last_updated"] = str(add_to_date(now_datetime(), days=-400))
		frappe.cache.hset("session", sid, session)

		response = self.rpc(self.anonymous(), "tools/list", token=token)

		self.assertEqual(response.status_code, 401)
		log = self.last_log(deny_reason="session_ended", user=USER_A)
		self.assertEqual((log.decision, log.principal), ("denied", "agent_token"))

	def test_token_sent_with_a_session_cookie_is_logged(self):
		client = self.login(USER_A)
		token = self.issue_token(client)

		response = self.rpc(client, "tools/list", token=token)

		self.assertEqual(response.status_code, 403)
		log = self.last_log(deny_reason="cookie_with_token", user=USER_A)
		self.assertEqual((log.decision, log.principal), ("denied", "agent_token"))

	def test_unknown_token_and_guest_are_not_logged(self):
		before = frappe.db.count("AI Action Log")

		self.rpc(self.anonymous(), "tools/list", token="fsat_unknown")
		self.rpc(self.anonymous(), "tools/list")

		self.assertEqual(frappe.db.count("AI Action Log"), before)
