"""Gerçek süreç üzerinden stdio MCP: initialize → initialized → tools/list → tools/call; CLI insan sınırları."""
import json
import os
import subprocess
import sys
import unittest

import support
from fake_press import FakePress, FakePressServer
from support import TempHome, make_config

SERVER = os.path.join(support.PACKAGE, "server.py")
EXPECTED_TOOLS = {"kit_status", "contract_search", "contract_get", "ui_reference_search", "press_read",
                  "press_triage_build", "press_propose", "proposal_get", "press_execute", "press_track",
                  "app_inspect", "app_check", "app_propose_change", "app_apply"}


class StdioSession:
    def __init__(self, config_path):
        self.proc = subprocess.Popen([sys.executable, "-I", SERVER, "serve", "--config", config_path],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.next_id = 0

    def send(self, payload):
        self.proc.stdin.write((json.dumps(payload) + "\n").encode())
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        return json.loads(self.proc.stdout.readline())

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()


class StdioTests(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.fake = FakePress(principal="team")
        self.server = FakePressServer(self.fake).__enter__()
        self.config_path, _ = make_config(self.home, self.server.url, workspace=self.home.workspace())
        self.session = StdioSession(self.config_path)

    def tearDown(self):
        self.session.close()
        self.server.__exit__(None, None, None)
        self.home.cleanup()

    def handshake(self, version="2025-06-18"):
        result = self.session.request("initialize", {"protocolVersion": version, "capabilities": {},
                                                     "clientInfo": {"name": "test", "version": "0"}})
        self.session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def test_full_handshake_list_and_call(self):
        init = self.handshake()
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(init["result"]["serverInfo"]["name"], "press-ai")
        self.assertIn("no approve tool", init["result"]["instructions"])
        tools = self.session.request("tools/list")["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, EXPECTED_TOOLS)
        for tool in tools:
            self.assertNotIn("approve", tool["name"])
            schema_text = json.dumps(tool["inputSchema"])
            for forbidden in ('"confirm"', '"approved"', '"force"', '"team"'):
                self.assertNotIn(forbidden, schema_text, tool["name"])
        status = self.session.request("tools/call", {"name": "kit_status", "arguments": {}})["result"]
        self.assertFalse(status["isError"])
        body = json.loads(status["content"][0]["text"])
        self.assertEqual(body["press"]["principal"], "team")
        self.assertNotIn(support.SECRET, status["content"][0]["text"])
        read = self.session.request("tools/call", {"name": "press_read",
                                                   "arguments": {"operation": "team.context", "params": {}}})["result"]
        self.assertFalse(read["isError"], read)
        self.assertIn("untrusted_data", read["content"][0]["text"])

    def test_tool_errors_are_results_not_crashes(self):
        self.handshake()
        bad = self.session.request("tools/call", {"name": "press_execute", "arguments": {"proposal_id": "p-" + "0" * 20}})
        self.assertTrue(bad["result"]["isError"])
        extra = self.session.request("tools/call", {"name": "press_propose", "arguments": {
            "operation": "site.backup", "params": {"site": "school.example.test"}, "confirm": True}})
        self.assertTrue(extra["result"]["isError"])
        self.assertIn("unexpected fields confirm", extra["result"]["content"][0]["text"])
        unknown = self.session.request("tools/call", {"name": "approve", "arguments": {}})
        self.assertEqual(unknown["error"]["code"], -32602)
        ping = self.session.request("ping")
        self.assertEqual(ping["result"], {})

    def test_requests_before_initialized_are_refused(self):
        self.session.request("initialize", {"protocolVersion": "2025-06-18"})
        early = self.session.request("tools/list")
        self.assertEqual(early["error"]["code"], -32002)

    def test_older_and_newer_protocol_versions(self):
        old = self.handshake("2024-11-05")
        self.assertEqual(old["result"]["protocolVersion"], "2024-11-05")
        self.assertNotIn("instructions", old["result"])
        tools = self.session.request("tools/list")["result"]["tools"]
        self.assertNotIn("annotations", tools[0])

    def test_newer_protocol_is_negotiated_down(self):
        result = self.handshake("2099-01-01")
        self.assertEqual(result["result"]["protocolVersion"], "2025-06-18")

    def test_malformed_input(self):
        self.session.proc.stdin.write(b"{not json\n")
        self.session.proc.stdin.flush()
        self.assertEqual(json.loads(self.session.proc.stdout.readline())["error"]["code"], -32700)
        self.session.send([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(json.loads(self.session.proc.stdout.readline())["error"]["code"], -32600)
        self.assertEqual(self.session.request("nope")["error"]["code"], -32601)

    def test_oversized_message_closes_transport(self):
        self.session.proc.stdin.write(b"x" * (512 * 1024 + 10) + b"\n")
        self.session.proc.stdin.flush()
        reply = json.loads(self.session.proc.stdout.readline())
        self.assertEqual(reply["error"]["code"], -32600)
        self.assertEqual(self.session.proc.wait(timeout=10), 0)


class CliHumanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.config_path, _ = make_config(self.home)

    def tearDown(self):
        self.home.cleanup()

    def run_cli(self, *args):
        # Onay ifadesi boru üzerinden verilse bile (TTY yok) komut reddetmeli.
        return subprocess.run([sys.executable, "-I", SERVER, *args, "--config", self.config_path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                              input=b"APPROVE 000000000000\n")

    def test_approve_requires_interactive_terminal(self):
        result = self.run_cli("approve", "p-" + "a" * 20)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"tty_required", result.stderr)

    def test_reject_and_resolve_require_interactive_terminal(self):
        self.assertIn(b"tty_required", self.run_cli("reject", "p-" + "a" * 20).stderr)
        self.assertIn(b"tty_required", self.run_cli("resolve", "p-" + "a" * 20, "--note", "x").stderr)

    def test_schemas_command(self):
        result = subprocess.run([sys.executable, "-I", SERVER, "schemas"], stdout=subprocess.PIPE, timeout=30)
        schemas = json.loads(result.stdout)
        self.assertIn("deploy.start", schemas)
        self.assertEqual(schemas["deploy.start"]["required"], ["build"])


if __name__ == "__main__":
    unittest.main()
