"""Identity: human session, agent token and MCP transport (G-148)."""

import hashlib

import frappe
from frappe.core.doctype.user.user import generate_keys

from platform_core.ai.tests.base import API, DOCTYPE, MANAGER, MCP_PATH, USER_A, AiTestCase

LATEST = "2026-07-28"


class TestIdentity(AiTestCase):
	def test_builtin_frappe_mcp_endpoint_is_closed(self):
		manager = self.login(MANAGER)

		response = self.send(
			manager, "POST", "/api/v2/mcp", body={"jsonrpc": "2.0", "id": 1, "method": "ping"}
		)

		self.assertEqual(response.status_code, 404)

	def test_guest_is_rejected(self):
		response = self.rpc(self.anonymous(), "tools/list")

		# Frappe refuses a guest on a whitelisted method with 403 before the layer runs. The endpoint
		# is not opened to guests, so the contract states 403 for a request without credentials.
		self.assertEqual(response.status_code, 403)

	def test_agent_token_acts_as_the_user_on_mcp_only(self):
		name = self.make_record(USER_A, title="Belirtecle")
		client = self.login(USER_A)
		token = self.issue_token(client)

		result = self.call_tool(
			self.anonymous(), "plt_get_document", {"doctype": DOCTYPE, "name": name}, token=token
		)
		elsewhere = self.send(
			self.anonymous(),
			"GET",
			f"/api/resource/{DOCTYPE}/{name}",
			headers={"Authorization": f"Bearer {token}"},
		)

		self.assertEqual(result["structuredContent"]["document"]["title"], "Belirtecle")
		log = self.last_log(tool="plt_get_document", target_name=name)
		self.assertEqual((log.user, log.principal), (USER_A, "agent_token"))
		self.assertEqual(elsewhere.status_code, 401)

	def test_token_response_matches_contract(self):
		client = self.login(USER_A)

		message = self.human(client, "POST", "issue_agent_token", body={}).json["message"]

		self.assertTrue(message["token"].startswith("fsat_"))
		self.assertEqual((message["expires_in"], message["max_calls"]), (300, 20))
		self.assertTrue(message["audience"])

	def test_token_cannot_issue_another_token(self):
		client = self.login(USER_A)
		token = self.issue_token(client)

		response = self.send(
			self.anonymous(),
			"POST",
			API + "issue_agent_token",
			body={},
			headers={"Authorization": f"Bearer {token}"},
		)

		self.assertEqual(response.status_code, 401)

	def test_unknown_token_is_rejected(self):
		response = self.rpc(self.anonymous(), "tools/list", token="fsat_bilinmeyen")

		self.assertEqual(response.status_code, 401)

	def test_cookie_together_with_token_is_rejected(self):
		client = self.login(USER_A)
		token = self.issue_token(client)

		response = self.rpc(client, "tools/list", token=token)

		self.assertEqual(response.status_code, 403)

	def test_token_dies_with_the_session(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		self.send(client, "POST", "/api/method/logout", body={})

		response = self.rpc(self.anonymous(), "tools/list", token=token)

		self.assertEqual(response.status_code, 401)

	def test_token_call_budget_is_enforced(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		anonymous = self.anonymous()

		for _ in range(20):
			self.call_tool(anonymous, "plt_search_doctypes", {"query": "YZ"}, token=token)
		response = self.rpc(
			anonymous, "tools/call", {"name": "plt_search_doctypes", "arguments": {}}, token=token
		)

		self.assertEqual(response.status_code, 401)
		log = self.last_log(deny_reason="token_call_limit")
		self.assertEqual((log.user, log.decision), (USER_A, "denied"))

	def test_api_key_is_not_accepted_on_mcp(self):
		keys = generate_keys(MANAGER)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		response = self.rpc(
			self.anonymous(),
			"tools/list",
			headers={"Authorization": f"token {keys['api_key']}:{keys['api_secret']}"},
		)

		self.assertEqual(response.status_code, 403)

	def test_legacy_handshake_and_tool_list(self):
		client = self.login(USER_A)

		initialized = self.rpc(
			client,
			"initialize",
			{
				"protocolVersion": "2025-11-25",
				"capabilities": {},
				"clientInfo": {"name": "t", "version": "1"},
			},
		).json["result"]
		tools = self.rpc(client, "tools/list").json["result"]["tools"]

		self.assertEqual(initialized["protocolVersion"], "2025-11-25")
		self.assertIn("tools", initialized["capabilities"])
		names = {tool["name"] for tool in tools}
		self.assertLessEqual(
			{
				"plt_search_doctypes",
				"plt_get_doctype_schema",
				"plt_list_documents",
				"plt_get_document",
				"plt_run_report",
				"plt_create_document",
				"plt_update_document",
				"plt_submit_document",
				"plt_cancel_document",
				"plt_delete_document",
				"plt_get_proposal",
			},
			names,
		)
		self.assertNotIn("call_method", names)

	def test_latest_protocol_revision(self):
		client = self.login(USER_A)
		meta = {
			"io.modelcontextprotocol/protocolVersion": LATEST,
			"io.modelcontextprotocol/clientCapabilities": {},
			"io.modelcontextprotocol/clientInfo": {"name": "sahte-istemci", "version": "1.0"},
		}
		headers = {"MCP-Protocol-Version": LATEST, "Mcp-Method": "tools/call", "Mcp-Name": "plt_search_doctypes"}

		ok = self.rpc(
			client,
			"tools/call",
			{"name": "plt_search_doctypes", "arguments": {"query": "YZ"}, "_meta": meta},
			headers={**headers, "Mcp-Conversation-Id": "konusma-1"},
		)
		mismatch = self.rpc(
			client,
			"tools/call",
			{"name": "plt_search_doctypes", "arguments": {}, "_meta": meta},
			headers={**headers, "Mcp-Name": "plt_get_document"},
		)
		discover = self.rpc(
			client, "server/discover", {"_meta": meta}, headers={**headers, "Mcp-Method": "server/discover"}
		)

		self.assertEqual(ok.status_code, 200)
		self.assertEqual(ok.json["result"]["resultType"], "complete")
		self.assertEqual(mismatch.status_code, 400)
		self.assertIn(LATEST, discover.json["result"]["supportedVersions"])
		# The conversation id is stored as its SHA-256.
		log = self.last_log(tool="plt_search_doctypes", session_id=hashlib.sha256(b"konusma-1").hexdigest())
		# An unknown client is stored under one common name, not under its own text.
		self.assertEqual(log.client_info, "other")

	def test_transport_rules(self):
		client = self.login(USER_A)

		get = self.send(client, "GET", MCP_PATH)
		foreign_origin = self.rpc(client, "ping", headers={"Origin": "https://kotu.example.test"})
		notification = self.send(
			client, "POST", MCP_PATH, body={"jsonrpc": "2.0", "method": "notifications/initialized"}
		)
		unknown_method = self.rpc(client, "resources/list")
		unknown_tool = self.rpc(client, "tools/call", {"name": "call_method", "arguments": {}})

		self.assertNotEqual(get.status_code, 200)
		self.assertEqual(foreign_origin.status_code, 403)
		self.assertEqual(notification.status_code, 202)
		self.assertEqual(unknown_method.status_code, 404)
		self.assertEqual(unknown_tool.status_code, 404)

	def test_no_tool_offers_an_approval_path(self):
		manager = self.login(MANAGER)

		tools = self.rpc(manager, "tools/list").json["result"]["tools"]

		for tool in tools:
			self.assertNotRegex(tool["name"], r"approve|confirm|resolve|reject")
			properties = set(tool["inputSchema"].get("properties", {}))
			self.assertFalse(
				properties & {"confirm", "confirmed", "approved", "approve", "force"}, tool["name"]
			)
			self.assertIs(tool["inputSchema"].get("additionalProperties"), False, tool["name"])
