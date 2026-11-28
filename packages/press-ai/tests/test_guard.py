"""Tool separation and authority (G-84, G-85).

- Commercial tools run with a team key on the Press dashboard API. Operation tools run with a
  System User key on the Desk API. One server process holds one of these identities.
- Tenant tools are not here. They run on the tenant site with the user's short agent token
  (`platform_core.ai`), and that endpoint refuses Press API keys
  (`test_api_key_is_not_accepted_on_mcp`).
- The tool list shows only the tools whose part is configured.
- Every refusal lands in the audit log with the tool, the reason and a digest of the arguments.
"""
import json
import os
import unittest

import support
from fake_press import FakePress, FakePressServer
from press_ai.config import Config
from press_ai.errors import ConfigError, KitError
from press_ai.tools import Context, Toolbox
from support import PressCase

PRESS_TOOLS = {"press_read", "press_triage_build", "press_propose", "press_execute", "press_track"}
APP_TOOLS = {"app_inspect", "app_check", "app_propose_change", "app_apply"}
TENANT_MCP = "platform_core.api.ai.mcp"


def audit_events(home):
    path = home.path("state", "audit.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class CommercialIdentity(PressCase):
    PRINCIPAL = "team"
    MUTATIONS = ("site.backup",)

    def test_commercial_proposal_cannot_run_with_the_operation_identity(self):
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        support.approve(self.ctx, proposal["proposal_id"])
        _, operator = support.make_config(self.home, self.server.url, "operator", "team-alpha", self.MUTATIONS)
        with self.assertRaises(KitError) as caught:
            Toolbox(Context(operator, clock=self.clock)).call("press_execute", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(caught.exception.code, "authority_changed")

    def test_team_key_uses_only_the_dashboard_api_with_its_team(self):
        self.call("press_read", operation="site.get", params={"site": "school.example.test"})
        self.assertTrue(self.fake.requests)
        for method, _, headers in self.fake.requests:
            self.assertFalse(method.startswith("frappe.client."), method)
            self.assertNotIn(TENANT_MCP, method)
            self.assertEqual(headers.get("X-Press-Team"), "team-alpha")


class OperationIdentity(PressCase):
    PRINCIPAL = "operator"

    def test_operation_reads_run_only_with_the_system_user_key(self):
        self.call("press_read", operation="error_log.list", params={})
        methods = self.methods()
        self.assertTrue(any(m.startswith("frappe.client.") for m in methods), methods)
        self.assertFalse(any(TENANT_MCP in m for m in methods), methods)



class OneIdentityPerProcess(unittest.TestCase):
    def setUp(self):
        self.home = support.TempHome()
        self.addCleanup(self.home.cleanup)

    def test_a_config_cannot_hold_two_principals(self):
        path, _ = support.make_config(self.home, "http://127.0.0.1:9", "team", "team-alpha")
        with open(path) as handle:
            data = json.load(handle)
        data["press"]["principal"] = ["team", "operator"]
        with open(path, "w") as handle:
            json.dump(data, handle)
        with self.assertRaises(ConfigError):
            Config.load(path)


class ToolListFollowsConfiguration(unittest.TestCase):
    def setUp(self):
        self.home = support.TempHome()
        self.addCleanup(self.home.cleanup)

    def names(self, url=None, workspace=None):
        _, config = support.make_config(self.home, url, workspace=workspace)
        return {tool["name"] for tool in Toolbox(Context(config)).describe()}

    def test_press_tools_are_hidden_without_press(self):
        names = self.names(workspace=self.home.workspace())
        self.assertFalse(names & PRESS_TOOLS, names)
        self.assertTrue(APP_TOOLS <= names, names)

    def test_app_tools_are_hidden_without_a_workspace(self):
        names = self.names(url="http://127.0.0.1:9")
        self.assertFalse(names & APP_TOOLS, names)
        self.assertTrue(PRESS_TOOLS <= names, names)

    def test_contract_tools_are_always_listed(self):
        names = self.names()
        self.assertEqual(names, {"kit_status", "contract_search", "contract_get", "ui_reference_search",
                                 "proposal_get"})

    def test_hidden_tool_is_refused_and_logged(self):
        _, config = support.make_config(self.home, None)
        tools = Toolbox(Context(config))
        with self.assertRaises(KitError) as caught:
            tools.call("press_read", {"operation": "site.get", "params": {"site": "school.example.test"}})
        self.assertEqual(caught.exception.code, "not_configured")
        self.assertEqual(audit_events(self.home)[-1]["reason"], "not_configured")


class RefusalsAreLogged(PressCase):
    PRINCIPAL = "team"

    def test_other_teams_site_refusal_is_in_the_audit_log_without_arguments(self):
        self.fake.sites["school.example.test"]["team"] = "team-beta"
        with self.assertRaises(KitError):
            self.call("press_read", operation="site.get", params={"site": "school.example.test"})
        event = audit_events(self.home)[-1]
        self.assertEqual((event["event"], event["tool"], event["reason"]), ("denied", "press_read", "press_permission"))
        self.assertEqual(event["principal"], "team")
        self.assertNotIn("school.example.test", json.dumps(event))

    def test_successful_read_is_not_a_denial(self):
        self.call("press_read", operation="site.get", params={"site": "school.example.test"})
        self.assertFalse([e for e in audit_events(self.home) if e.get("event") == "denied"])


class StdioUnknownToolIsLogged(unittest.TestCase):
    def test_unknown_tool_over_mcp_is_logged(self):
        from press_ai.mcp_stdio import Server

        home = support.TempHome()
        self.addCleanup(home.cleanup)
        fake = FakePress(principal="team")
        server = FakePressServer(fake).__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        _, config = support.make_config(home, server.url)
        mcp = Server(Toolbox(Context(config)))
        mcp.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                    "params": {"protocolVersion": "2025-06-18"}}))
        mcp.handle_line(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        reply = mcp.handle_line(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                            "params": {"name": "approve", "arguments": {}}}))
        self.assertEqual(reply["error"]["code"], -32602)
        event = audit_events(home)[-1]
        self.assertEqual((event["event"], event["tool"], event["reason"]), ("denied", "approve", "unknown_tool"))


if __name__ == "__main__":
    unittest.main()
