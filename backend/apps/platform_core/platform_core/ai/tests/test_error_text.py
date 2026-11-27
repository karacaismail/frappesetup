"""A tool's own error text never reaches the response, the proposal record or the action log.

An app tool may put a field value into the text of a Frappe error. That value can be personal
data. The layer answers with a fixed code and a fixed, translated text. The detail goes to the
server log as the tool name and the error type only.
"""

import json
from unittest.mock import patch

import frappe

from platform_core.ai.errors import CONTEXT, SERVER_LOG
from platform_core.ai.tests import sample_tools_errors as samples
from platform_core.ai.tests.base import USER_A, AiTestCase, answer_text

HOOK = "platform_core.ai.tests.sample_tools_errors.declare"
MARKER = samples.MARKER


def with_tools():
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		return [HOOK] if hook == "ai_tools" else original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


def stored_text() -> str:
	"""Everything the layer and the error log stored, as one text."""
	frappe.db.rollback()
	rows = []
	for doctype in ("PLT AI Action Proposal", "PLT AI Action Log", "Error Log"):
		rows += frappe.get_all(doctype, fields=["*"])
	return json.dumps(rows, default=str)


class TestToolErrorText(AiTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Error Log")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

	def test_preview_errors_answer_with_a_fixed_text(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		expected = {
			"plt_leaky_validation": ("invalid_arguments", "The tool refused the input."),
			"plt_leaky_permission": ("permission", "You do not have permission for this action."),
			"plt_leaky_missing": ("not_found", "The record was not found."),
		}

		with with_tools():
			for tool, (code, text) in expected.items():
				response = self.rpc(client, "tools/call", {"name": tool, "arguments": {"name": name}})
				raw = response.get_data(as_text=True)
				result = response.json["result"]
				self.assertNotIn(MARKER, raw, tool)
				self.assert_denied(result, code)
				self.assertEqual(result["structuredContent"]["error"]["message"], answer_text(text, USER_A), tool)

		self.assertNotIn(MARKER, stored_text())

	def test_fixed_text_follows_the_language_of_the_user(self):
		"""The same refusal is English for an English user and the Turkish row for a Turkish user."""
		name = self.make_record(USER_A)
		source = "The tool refused the input."
		original = frappe.db.get_value("User", USER_A, "language")
		self.addCleanup(self.set_language, USER_A, original)
		answers = {}

		for lang in ("en", "tr"):
			self.set_language(USER_A, lang)
			client = self.login(USER_A)
			with with_tools():
				response = self.rpc(client, "tools/call", {"name": "plt_leaky_validation", "arguments": {"name": name}})
			answers[lang] = response.json["result"]["structuredContent"]["error"]["message"]

		self.assertEqual(answers["en"], source)
		self.assertEqual(answers["tr"], frappe._(source, lang="tr", context=CONTEXT))
		self.assertNotEqual(answers["tr"], source)

	def set_language(self, user: str, lang: str | None) -> None:
		frappe.db.set_value("User", user, "language", lang)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		frappe.clear_cache(user=user)

	def test_execution_errors_store_a_fixed_code(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		expected = {
			"plt_leaky_handler": "validation_error",
			"plt_leaky_permission_handler": "permission",
		}

		with with_tools():
			for tool, code in expected.items():
				result = self.call_tool(client, tool, {"name": name})
				proposal_id = result["structuredContent"]["proposal_id"]
				response = self.approve(client, proposal_id)
				self.assertNotIn(MARKER, response.get_data(as_text=True), tool)
				self.assertEqual(response.json["message"]["proposal"]["error"], code, tool)
				self.assertEqual(frappe.db.get_value("PLT AI Action Proposal", proposal_id, "error"), code)
				self.human(
					client, "POST", "resolve_proposal", body={"proposal_id": proposal_id, "outcome": "failed"}
				)

		self.assertNotIn(MARKER, stored_text())

	def test_server_log_names_the_tool_and_the_error_type_without_the_text(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)

		with with_tools(), self.assertLogs(f"{SERVER_LOG}-all", level="WARNING") as captured:
			self.rpc(
				client, "tools/call", {"name": "plt_leaky_validation", "arguments": {"name": name}}
			)

		text = "\n".join(captured.output)
		self.assertIn("plt_leaky_validation", text)
		self.assertIn("ValidationError", text)
		self.assertNotIn(MARKER, text)
