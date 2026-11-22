"""MCP OAuth HTTP acceptance with a simulated identity provider."""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.core.doctype.user.user import generate_keys
from frappe.utils import get_test_client

from platform_core.ai.tests.base import API, DOCTYPE, MCP_PATH, USER_A, USER_B, AiTestCase
from platform_core.identity.api import KeycloakKeysUnavailable, ServiceTokenRejected

RESOURCE = "https://tenant.example.test/api/method/platform_core.api.ai.mcp"
ISSUER = "https://identity.example.test/realms/platform"
METADATA = "/api/method/platform_core.api.ai.mcp_resource_metadata"
CONFIG = {"resource": RESOURCE, "issuer": ISSUER}


class TestMcpOAuth(AiTestCase):
	def setUp(self):
		super().setUp()
		self.bearer = f"synthetic.{uuid4().hex}.credential"
		settings = patch("platform_core.identity.api.mcp_oauth_config", create=True, return_value=CONFIG)
		settings.start()
		self.addCleanup(settings.stop)
		now = int(time.time())
		identity = patch(
			"platform_core.identity.api.verify_mcp_token",
			create=True,
			return_value={
				"account": USER_A,
				"issuer": ISSUER,
				"resource": RESOURCE,
				"client_id": "external-test",
				"issued_at": now,
				"expires_at": now + 300,
			},
		)
		self.verify = identity.start()
		self.addCleanup(identity.stop)

	def test_discovery_and_unwrapped_metadata(self):
		response = self.rpc(self.anonymous(), "tools/list")
		self.assertEqual(response.status_code, 401)
		self.assertEqual(
			response.headers["WWW-Authenticate"],
			f'Bearer resource_metadata="https://tenant.example.test{METADATA}", scope="mcp"',
		)
		metadata = self.send(self.anonymous(), "GET", METADATA, headers={"X-Forwarded-Host": "wrong.test"})
		self.assertEqual(metadata.status_code, 200)
		self.assertEqual(
			metadata.json,
			{
				"resource": RESOURCE,
				"authorization_servers": [ISSUER],
				"scopes_supported": ["mcp"],
				"bearer_methods_supported": ["header"],
			},
		)
		self.verify.assert_not_called()

	def test_disabled_keeps_guest_refusal_and_hides_metadata(self):
		with patch("platform_core.identity.api.mcp_oauth_config", return_value=None):
			guest = self.rpc(self.anonymous(), "tools/list")
			metadata = self.send(self.anonymous(), "GET", METADATA)
		self.assertEqual(guest.status_code, 403)
		self.assertNotIn(METADATA, guest.headers.get("WWW-Authenticate", ""))
		self.assertEqual(metadata.status_code, 404)

	def test_http_tool_enforces_ownership(self):
		own = self.make_record(USER_A, title="Own")
		foreign = self.make_record(USER_B, title="Foreign")
		for name, allowed in ((own, True), (foreign, False)):
			with self.subTest(allowed=allowed):
				result = self.call_tool(
					self.anonymous(),
					"plt_get_document",
					{"doctype": DOCTYPE, "name": name},
					token=self.bearer,
				)
				if allowed:
					self.assertEqual(result["structuredContent"]["document"]["title"], "Own")
				else:
					self.assertTrue(result["isError"])
		self.verify.assert_called_with(self.bearer)

	def test_oauth_write_opens_a_proposal_without_changing_the_document(self):
		name = self.make_record(USER_A, title="Before")
		arguments = {"doctype": DOCTYPE, "name": name, "data": {"title": "After"}}
		result = self.call_tool(self.anonymous(), "plt_update_document", arguments, token=self.bearer)
		self.assertFalse(result["isError"], result)
		self.assertEqual(result["structuredContent"]["status"], "approval_required")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Before")
		log = self.last_log(tool="plt_update_document", target_name=name)
		self.assertEqual((log.principal, log.approval_state), ("oauth", "pending"))

	def test_credential_is_bound_to_exact_post_route_without_cmd_or_cookie(self):
		headers = {"Authorization": f"Bearer {self.bearer}"}
		for path in (
			API + "approve_proposal",
			"/api/resource/User",
			METADATA,
			MCP_PATH + "/",
			MCP_PATH.replace("/api/", "/api/v1/"),
		):
			with self.subTest(path=path):
				response = self.send(self.anonymous(), "POST", path, body={}, headers=headers)
				self.assertEqual(response.status_code, 401)
		for suffix in ("?cmd=platform_core.api.ai.approve_proposal", "?access_token=synthetic"):
			response = self.send(self.anonymous(), "POST", MCP_PATH + suffix, body={}, headers=headers)
			self.assertEqual(response.status_code, 401, response.get_data(as_text=True))
		self.assertEqual(self.rpc(self.login(USER_A), "tools/list", token=self.bearer).status_code, 403)
		guest = self.send(self.anonymous(), "POST", MCP_PATH, body={"access_token": self.bearer})
		self.assertEqual(guest.status_code, 401)
		self.verify.assert_not_called()

	def test_provider_unavailable_returns_503(self):
		self.verify.side_effect = KeycloakKeysUnavailable("MCP identity provider unavailable.")
		response = self.rpc(self.anonymous(), "tools/list", token=self.bearer)
		self.assertEqual(response.status_code, 503)
		self.assertNotIn(self.bearer, response.get_data(as_text=True))

	def test_expired_and_call_allowance(self):
		error = ServiceTokenRejected("Rejected")
		error.reason = "expired"
		self.verify.side_effect = error
		with patch("platform_core.ai.oauth.frappe.logger") as logger:
			response = self.rpc(self.anonymous(), "tools/list", token=self.bearer)
			self.assertEqual(response.status_code, 401)
			logger.return_value.warning.assert_called_once_with("token_expired")
		self.verify.side_effect = None
		for _iteration in range(20):
			self.call_tool(self.anonymous(), "plt_search_doctypes", {"query": "PLT"}, token=self.bearer)
		response = self.rpc(
			self.anonymous(), "tools/call", {"name": "plt_search_doctypes"}, token=self.bearer
		)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(self.last_log(deny_reason="token_call_limit").user, USER_A)

	def test_parallel_first_calls_and_cache_loss_keep_the_same_budget(self):
		headers = {"Authorization": f"Bearer {self.bearer}", "Accept": "application/json"}
		payload = {
			"jsonrpc": "2.0",
			"id": 1,
			"method": "tools/call",
			"params": {"name": "plt_search_doctypes", "arguments": {"query": "PLT"}},
		}

		def call(_index):
			client = get_test_client(use_cookies=False)
			response = client.post(MCP_PATH, json=payload, headers=headers)
			if response.status_code == 200:
				self.assertFalse(response.json["result"]["isError"], response.json)
			return response.status_code

		frappe.db.commit()  # nosemgrep: frappe-request-commit -- HTTP setup uses other connections
		with patch("frappe.app.get_site_name", return_value=self.site), ThreadPoolExecutor(6) as pool:
			results = list(pool.map(call, range(21)))
		self.assertEqual(sorted(results), [200] * 20 + [401])

		digest = hashlib.sha256(f"external-test\0{self.bearer}".encode()).hexdigest()
		frappe.cache.delete(frappe.cache.make_key(f"mcp_oauth_admitted:{digest}"))
		self.assertEqual(
			self.rpc(self.anonymous(), "tools/call", payload["params"], token=self.bearer).status_code, 401
		)

	def test_lost_database_counter_cannot_reissue_an_allowance(self):
		arguments = {"query": "PLT"}
		self.call_tool(self.anonymous(), "plt_search_doctypes", arguments, token=self.bearer)
		digest = hashlib.sha256(f"external-test\0{self.bearer}".encode()).hexdigest()
		frappe.db.delete("PLT MCP Call Budget", {"name": digest})
		params = {"name": "plt_search_doctypes", "arguments": arguments}
		response = self.rpc(self.anonymous(), "tools/call", params, token=self.bearer)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(self.last_log(deny_reason="token_call_state_lost").user, USER_A)

	def test_human_agent_and_api_key_behaviors_are_preserved(self):
		human = self.login(USER_A)
		self.assertEqual(self.rpc(human, "tools/list").status_code, 200)
		agent_token = self.issue_token(human)
		self.assertEqual(self.rpc(self.anonymous(), "tools/list", token=agent_token).status_code, 200)
		keys = generate_keys(USER_A)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- HTTP setup uses another connection
		headers = {"Authorization": f"token {keys['api_key']}:{keys['api_secret']}"}
		self.assertEqual(self.rpc(self.anonymous(), "tools/list", headers=headers).status_code, 403)
		key_identity = self.send(
			self.anonymous(), "GET", "/api/method/frappe.auth.get_logged_user", headers=headers
		)
		self.assertEqual(key_identity.status_code, 200)
		self.assertEqual(key_identity.json["message"], USER_A)
		self.verify.assert_not_called()
