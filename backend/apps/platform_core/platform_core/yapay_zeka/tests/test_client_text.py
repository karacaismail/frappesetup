"""Text the client sends about itself is not stored as it came.

A client may put a credential into the conversation id or into its name or version by mistake.
The layer stores a digest of the conversation id. It stores the client's name and version only
if they have the allowed shape. Nothing else of that text reaches a record or a response.
"""

import hashlib
import json

import frappe

from platform_core.yapay_zeka.tests.base import DOCTYPE, MCP_PATH, USER_A, YzTestCase

# A made-up value shaped like a credential.
FAKE_TOKEN = "fsat_Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZg"
LATEST = "2026-07-28"


def stored_text() -> str:
	frappe.db.rollback()
	rows = frappe.get_all("AI Action Log", fields=["*"]) + frappe.get_all("AI Action Proposal", fields=["*"])
	return json.dumps(rows, default=str)


class TestClientText(YzTestCase):
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

		self.call(client, "search_doctypes", {}, conversation="conversation-1", name="client", version="1.0")
		proposed = self.call(
			client,
			"update_document",
			{"doctype": DOCTYPE, "name": record, "data": {"title": "New"}},
			conversation="conversation-1",
			name="client",
			version="1.0",
		)

		proposal_id = proposed.json["result"]["structuredContent"]["proposal_id"]
		self.assertTrue(self.last_log(tool="search_doctypes", session_id=digest))
		self.assertEqual(frappe.db.get_value("AI Action Proposal", proposal_id, "session_id"), digest)
		self.assertNotIn("conversation-1", stored_text())

	def test_fake_token_leaves_no_trace_in_records_or_responses(self):
		client = self.login(USER_A)
		responses = [
			self.call(client, "search_doctypes", {}, conversation=FAKE_TOKEN, name="client", version="1.0"),
			self.call(client, "search_doctypes", {}, conversation="c", name="client", version=FAKE_TOKEN),
			self.call(client, "search_doctypes", {}, conversation="c", name=FAKE_TOKEN, version="1.0"),
			self.call(
				client, "search_doctypes", {}, conversation="c", name=f"client {FAKE_TOKEN}", version="1"
			),
			self.call(
				client, "no_such_tool", {}, conversation=FAKE_TOKEN, name=FAKE_TOKEN, version=FAKE_TOKEN
			),
		]

		for response in responses:
			self.assertNotIn(FAKE_TOKEN, response.get_data(as_text=True))
		self.assertNotIn(FAKE_TOKEN, stored_text())
		self.assertGreaterEqual(len(self.new_logs()), 5)

	def test_client_name_and_version_of_the_allowed_shape_are_stored(self):
		client = self.login(USER_A)
		cases = {
			("mcp-inspector", "0.14.2"): "mcp-inspector 0.14.2",
			("Visual Studio Code", "1.99.0-insider"): "Visual Studio Code 1.99.0-insider",
			("client", "not a version"): "client",
			("client", ""): "client",
			("bad\nname", "1.0"): None,
			("x" * 41, "1.0"): None,
			("a-word-that-is-longer-than-24-chars", "1.0"): None,
		}

		for index, ((name, version), expected) in enumerate(cases.items()):
			conversation = f"shape-{index}"
			self.call(client, "search_doctypes", {}, conversation=conversation, name=name, version=version)
			log = self.last_log(session_id=hashlib.sha256(conversation.encode()).hexdigest())
			self.assertEqual(log.client_info, expected, (name, version))

	def new_logs(self) -> list[str]:
		frappe.db.rollback()
		return [name for name in frappe.get_all("AI Action Log", pluck="name") if name not in self.known_logs]

	def test_field_descriptions_say_what_is_stored(self):
		for doctype in ("AI Action Log", "AI Action Proposal"):
			self.assertIn("SHA-256", frappe.get_meta(doctype).get_field("session_id").description)
		self.assertNotIn("Untrusted", frappe.get_meta("AI Action Log").get_field("client_info").description)
		self.assertTrue(MCP_PATH)
