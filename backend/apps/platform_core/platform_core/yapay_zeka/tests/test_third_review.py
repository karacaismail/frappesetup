"""Rules decided after the third independent review.

B3: `failed` is only for the layer's own check. Any error after an app tool's `prepare` starts is `unknown`.
B6: an early MCP refusal of a known identity, such as a forbidden Origin, is logged and the row survives.
Y1: a tool that declares `versioned` must preview the target DocType, name and version.
"""

from unittest.mock import patch

import frappe
from frappe.core.doctype.user.user import generate_keys

from platform_core.yapay_zeka.tests import sample_tools
from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, MCP_PATH, USER_A, YzTestCase

HOOK = "platform_core.yapay_zeka.tests.sample_tools.declare_strict"
FOREIGN_ORIGIN = "https://other-site.example.test"


def with_strict_tools():
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		return [HOOK] if hook == "ai_tools" else original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


class TestAppPrepareIsNotTheLayersCheck(YzTestCase):
	def test_prepare_that_leaves_an_external_effect_stays_unknown(self):
		frappe.cache.delete_value(sample_tools.EXTERNAL_MARKER)
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		arguments = {"name": name, "title": "New"}

		with with_strict_tools():
			proposal = self.call_tool(client, "platform_core_effect_in_prepare", arguments)[
				"structuredContent"
			]
			outcome = self.approve(client, proposal["proposal_id"]).json["message"]
			again = self.call_tool(client, "platform_core_effect_in_prepare", arguments)

		self.assertEqual(frappe.cache.get_value(sample_tools.EXTERNAL_MARKER), name)
		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["proposal"]["result"], "unknown")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")
		self.assert_denied(again, "unresolved_unknown")
		log = self.last_log(proposal=proposal["proposal_id"], stage="execute")
		self.assertEqual((log.decision, log.result), ("error", "unknown"))


class TestVersionedPreviewIsComplete(YzTestCase):
	def test_versioned_tool_without_a_previewed_version_opens_no_proposal(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		# The record is new, so a proposal aimed at it can only come from this test.
		aimed_here = {"tool": "platform_core_versioned_without_version", "target_name": name}

		with with_strict_tools():
			result = self.call_tool(
				client, "platform_core_versioned_without_version", {"name": name, "title": "New"}
			)

		self.assert_denied(result, "invalid_preview")
		self.assertEqual(frappe.db.count("AI Action Proposal", aimed_here), 0)
		self.assertEqual(frappe.db.count("AI Action Proposal", {"args_json": ("like", f"%{name}%")}), 0)
		self.assertEqual(
			self.last_log(tool="platform_core_versioned_without_version").deny_reason, "invalid_preview"
		)

	def test_versioned_tool_that_loses_its_target_is_stopped_before_execution(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_strict_tools():
			proposal = self.call_tool(
				client, "platform_core_versioned_sometimes", {"name": name, "title": "New"}
			)
			proposal_id = proposal["structuredContent"]["proposal_id"]
			digest = self.digest_of(client, proposal_id)
			frappe.db.set_value(DOCTYPE, name, "amount", 99, update_modified=False)
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertEqual((outcome["executed"], outcome["deny_reason"]), (False, "invalid_preview"))
		self.assertEqual(outcome["proposal"]["status"], "rejected")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_pre_check_refuses_an_incomplete_versioned_preview(self):
		"""The same check runs right before execution, even if the approval check was skipped."""
		from platform_core.yapay_zeka import proposals, registry
		from platform_core.yapay_zeka.errors import ToolDenied

		name = self.make_record(USER_A, title="Old")
		frappe.set_user(USER_A)
		with with_strict_tools():
			frappe.local.yz_tools = None
			tool = registry.find("platform_core_versioned_without_version")
			stored = frappe._dict(target_doctype=None, target_name=None, target_modified=None)

			with self.assertRaises(ToolDenied) as raised:
				proposals._pre_check(stored, tool, {"name": name, "title": "New"})

		self.assertEqual(raised.exception.code, "invalid_preview")


class TestEarlyMcpRefusalsAreLogged(YzTestCase):
	def test_forbidden_origin_of_a_session_user_is_logged(self):
		client = self.login(USER_A)

		response = self.rpc(client, "tools/list", headers={"Origin": FOREIGN_ORIGIN})

		self.assertEqual(response.status_code, 403)
		log = self.last_log(deny_reason="origin_not_allowed", user=USER_A)
		self.assertEqual((log.decision, log.principal, log.stage), ("denied", "human_session", "auth"))

	def test_forbidden_origin_of_a_token_user_is_logged(self):
		token = self.issue_token(self.login(USER_A))

		response = self.rpc(self.anonymous(), "tools/list", token=token, headers={"Origin": FOREIGN_ORIGIN})

		self.assertEqual(response.status_code, 403)
		log = self.last_log(deny_reason="origin_not_allowed", user=USER_A)
		self.assertEqual((log.decision, log.principal), ("denied", "agent_token"))

	def test_forbidden_origin_of_an_api_key_user_is_logged(self):
		keys = generate_keys(MANAGER)
		frappe.db.commit()  # nosemgrep
		headers = {"Authorization": f"token {keys['api_key']}:{keys['api_secret']}", "Origin": FOREIGN_ORIGIN}

		response = self.rpc(self.anonymous(), "tools/list", headers=headers)

		self.assertEqual(response.status_code, 403)
		log = self.last_log(deny_reason="origin_not_allowed", user=MANAGER)
		self.assertEqual((log.decision, log.principal), ("denied", "other"))

	def test_other_early_refusals_of_a_known_user_are_logged(self):
		client = self.login(USER_A)

		wrong_type = self.send(client, "POST", MCP_PATH, headers={"Content-Type": "text/plain"})
		unknown_method = self.rpc(client, "resources/list")

		self.assertEqual((wrong_type.status_code, unknown_method.status_code), (415, 404))
		rows = frappe.get_all(
			"AI Action Log",
			filters={
				"deny_reason": "protocol_error",
				"user": USER_A,
				"name": ("not in", list(self.known_logs) or [""]),
			},
		)
		self.assertEqual(len(rows), 2)

	def test_early_refusal_of_a_guest_is_not_logged(self):
		before = frappe.db.count("AI Action Log")

		self.rpc(self.anonymous(), "tools/list", headers={"Origin": FOREIGN_ORIGIN})

		self.assertEqual(frappe.db.count("AI Action Log"), before)
