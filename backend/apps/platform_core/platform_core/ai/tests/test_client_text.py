"""Text the client sends about itself is not stored as it came.

A client may put a credential into the conversation id or into its name or version by mistake.
The layer stores a digest of the conversation id. It stores the client's name and version only
if they have the allowed shape. Nothing else of that text reaches a record or a response.
"""

import hashlib
import json

import frappe

from platform_core.ai.tests.base import DOCTYPE, MCP_PATH, USER_A, AiTestCase

# A made-up value shaped like a credential.
# Built from a repeated pair, so that a secret scanner does not take it for a real credential.
FAKE_TOKEN = "fsat_" + "x1" * 20
LATEST = "2026-07-28"


def stored_text() -> str:
	frappe.db.rollback()
	rows = frappe.get_all("PLT AI Action Log", fields=["*"]) + frappe.get_all("PLT AI Action Proposal", fields=["*"])
	return json.dumps(rows, default=str)


class TestClientText(AiTestCase):
	def call(self, client, tool: str, arguments: dict, *, conversation: str, name: str, version: str):
		meta = {
			"io.modelcontextprotocol/protocolVersion": LATEST,
			"io.modelcontextprotocol/clientInfo": {"name": name, "version": version},
			"io.modelcontextprotocol/clientCapabilities": {},
		}
		headers = {
			"MCP-Protocol-Version": LATEST,
			"Mcp-Method": "tools/call",
			"Mcp-Name": tool,
			"Mcp-Conversation-Id": conversation,
		}
		params = {"name": tool, "arguments": arguments, "_meta": meta}
		return self.rpc(client, "tools/call", params, headers=headers)

	def test_conversation_id_is_stored_as_a_digest(self):
		record = self.make_record(USER_A)
		client = self.login(USER_A)
		digest = hashlib.sha256(b"conversation-1").hexdigest()

		self.call(client, "plt_search_doctypes", {}, conversation="conversation-1", name="client", version="1.0")
		proposed = self.call(
			client,
			"plt_update_document",
			{"doctype": DOCTYPE, "name": record, "data": {"title": "New"}},
			conversation="conversation-1",
			name="client",
			version="1.0",
		)

		proposal_id = proposed.json["result"]["structuredContent"]["proposal_id"]
		self.assertTrue(self.last_log(tool="plt_search_doctypes", session_id=digest))
		self.assertEqual(frappe.db.get_value("PLT AI Action Proposal", proposal_id, "session_id"), digest)
		self.assertNotIn("conversation-1", stored_text())

	def test_fake_token_leaves_no_trace_in_records_or_responses(self):
		client = self.login(USER_A)
		responses = [
			self.call(client, "plt_search_doctypes", {}, conversation=FAKE_TOKEN, name="client", version="1.0"),
			self.call(client, "plt_search_doctypes", {}, conversation="c", name="client", version=FAKE_TOKEN),
			self.call(client, "plt_search_doctypes", {}, conversation="c", name=FAKE_TOKEN, version="1.0"),
			self.call(
				client, "plt_search_doctypes", {}, conversation="c", name=f"client {FAKE_TOKEN}", version="1"
			),
			self.call(
				client, "no_such_tool", {}, conversation=FAKE_TOKEN, name=FAKE_TOKEN, version=FAKE_TOKEN
			),
		]

		for response in responses:
			self.assertNotIn(FAKE_TOKEN, response.get_data(as_text=True))
		self.assertNotIn(FAKE_TOKEN, stored_text())
		self.assertGreaterEqual(len(self.new_logs()), 5)

	def test_only_a_fixed_name_of_a_known_client_is_stored(self):
		"""Free text of the client is never stored, even when it looks harmless."""
		client = self.login(USER_A)
		cases = {
			("mcp-inspector", "0.14.2"): "mcp-inspector",
			("MCP-Inspector", "1.0"): "mcp-inspector",
			("mcp", "2.3.0"): "mcp-sdk",
			# Made-up personal data and a short secret that fit every shape rule.
			("Jane Example", "1.0"): "other",
			("client", "1.0-s3cr3t"): "other",
			("mcp-inspector for Jane Example", "1.0"): "other",
			("x" * 41, "1.0"): "other",
		}

		for index, ((name, version), expected) in enumerate(cases.items()):
			conversation = f"shape-{index}"
			self.call(client, "plt_search_doctypes", {}, conversation=conversation, name=name, version=version)
			log = self.last_log(session_id=hashlib.sha256(conversation.encode()).hexdigest())
			self.assertEqual(log.client_info, expected, (name, version))

		text = stored_text()
		for leaked in ("Jane Example", "s3cr3t", "0.14.2", "2.3.0"):
			self.assertNotIn(leaked, text)

	def test_unknown_tool_name_leaves_no_trace_in_records_or_responses(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		name = "tool for Jane Example " + FAKE_TOKEN

		by_session = self.rpc(client, "tools/call", {"name": name, "arguments": {}})
		for _iteration in range(21):
			by_token = self.rpc(self.anonymous(), "tools/call", {"name": name, "arguments": {}}, token=token)

		self.assertEqual((by_session.status_code, by_token.status_code), (404, 401))
		self.assertEqual(by_session.json["error"]["message"], "Unknown tool.")
		for response in (by_session, by_token):
			self.assertNotIn("Jane Example", response.get_data(as_text=True))
			self.assertNotIn(FAKE_TOKEN, response.get_data(as_text=True))
		text = stored_text()
		self.assertNotIn("Jane Example", text)
		self.assertNotIn(FAKE_TOKEN, text)
		reasons = {
			row.deny_reason
			for row in frappe.get_all("PLT AI Action Log", fields=["name", "deny_reason", "tool"])
			if row.name not in self.known_logs and not row.tool
		}
		self.assertLessEqual({"unknown_tool", "token_call_limit"}, reasons)

	def new_logs(self) -> list[str]:
		frappe.db.rollback()
		return [name for name in frappe.get_all("PLT AI Action Log", pluck="name") if name not in self.known_logs]

	def test_field_descriptions_say_what_is_stored(self):
		for doctype in ("PLT AI Action Log", "PLT AI Action Proposal"):
			self.assertIn("SHA-256", frappe.get_meta(doctype).get_field("session_id").description)
		self.assertNotIn("Untrusted", frappe.get_meta("PLT AI Action Log").get_field("client_info").description)
		self.assertTrue(MCP_PATH)
