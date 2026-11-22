"""Run CronHR checks against a seeded, isolated Frappe HTTP server."""

import argparse
import json
import os
import re
import unittest
from datetime import date, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

LEAVE_PATH = "/api/resource/Leave%20Application"


class Client:
    def __init__(self, case, user):
        self.base = case.base
        self.site = case.site
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        status, _ = self.send("/api/method/login", {"usr": user, "pwd": case.password})
        case.assertEqual(status, 200, f"Synthetic login failed for {user}")

    def csrf_token(self):
        request = Request(
            self.base + "/desk", headers={"X-Frappe-Site-Name": self.site}
        )
        with self.opener.open(request, timeout=15) as response:
            match = re.search(rb'frappe\.csrf_token\s*=\s*"([^"]+)"', response.read())
        if match is None:
            raise AssertionError("Frappe Desk did not provide a CSRF token.")
        return match[1].decode()

    def send(self, path, data=None, csrf_token=None):
        headers = {"Accept": "application/json", "X-Frappe-Site-Name": self.site}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if csrf_token:
            headers["X-Frappe-CSRF-Token"] = csrf_token
        request = Request(
            self.base + path,
            json.dumps(data).encode() if data is not None else None,
            headers,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)


class LeaveHttpTest(unittest.TestCase):
    def login(self, actor):
        return Client(self, self.data["users"][actor])

    def document(self, client, key, status=200):
        name = quote(self.data["leaves"][key], safe="")
        code, result = client.send(f"{LEAVE_PATH}/{name}")
        self.assertEqual(code, status, result.get("exc_type"))
        return result.get("data")

    def listed(self, client):
        query = urlencode({"fields": json.dumps(["name"]), "limit_page_length": 100})
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exc_type"))
        return {row["name"] for row in result["data"]}

    def test_employee_sees_only_own_leave_and_no_balance(self):
        client = self.login("employee")
        self.assertEqual(
            self.listed(client),
            {self.data["leaves"][key] for key in ("employee", "ai")},
        )
        self.assertNotIn("leave_balance", self.document(client, "employee"))
        query = urlencode({"fields": json.dumps(["name", "leave_balance"])})
        code, payload = client.send(f"{LEAVE_PATH}?{query}")
        self.assertIn(code, (200, 403, 417), payload.get("exc_type"))
        if code == 200:
            self.assertTrue(all("leave_balance" not in row for row in payload["data"]))
        self.document(client, "outsider", 403)
        self.assertEqual(
            client.send(
                "/api/method/cronhr.api.approve_leave",
                {"name": self.data["leaves"]["employee"]},
            )[0],
            403,
        )

    def test_z_employee_can_create_draft_with_team_approver(self):
        client = self.login("employee")
        own = self.document(client, "employee")
        day = (date.fromisoformat(own["from_date"]) + timedelta(days=8)).isoformat()
        draft = {key: own[key] for key in ("employee", "company", "leave_type")}
        draft.update(
            from_date=day,
            to_date=day,
            status="Open",
            leave_approver=self.data["users"]["manager"],
        )
        code, result = client.send(LEAVE_PATH, draft, csrf_token=client.csrf_token())
        self.assertEqual(code, 200, result.get("exception"))
        self.assertEqual(
            result["data"]["leave_approver"], self.data["users"]["manager"]
        )

    def test_manager_can_only_approve_team_leave(self):
        client = self.login("manager")
        self.assertEqual(
            self.listed(client),
            {self.data["leaves"][key] for key in ("employee", "manager", "ai")},
        )
        self.assertEqual(self.document(client, "employee")["leave_balance"], 7)
        self.document(client, "outsider", 403)
        endpoint = "/api/method/cronhr.api.approve_leave"
        self.assertEqual(
            client.send(endpoint, {"name": self.data["leaves"]["outsider"]})[0], 403
        )
        self.assertEqual(
            client.send(endpoint, {"name": self.data["leaves"]["manager"]})[0], 403
        )
        code, result = client.send(endpoint, {"name": self.data["leaves"]["employee"]})
        self.assertEqual(code, 200, result.get("exc_type"))
        doc = self.document(client, "employee")
        self.assertEqual((doc["status"], doc["docstatus"]), ("Approved", 1))

    def test_hr_can_read_all_leaves(self):
        client = self.login("hr")
        self.assertEqual(self.listed(client), set(self.data["leaves"].values()))
        self.assertEqual(self.document(client, "outsider")["leave_balance"], 7)

    def test_ai_tool_writes_only_after_human_approval(self):
        if not self.with_ai:
            self.skipTest("Platform Core AI pending merge")
        client = self.login("manager")
        before = self.document(client, "ai")
        code, response = client.send(
            "/api/method/platform_core.api.ai.mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "cronhr_approve_leave",
                    "arguments": {
                        "name": before["name"],
                        "version": before["modified"],
                    },
                },
            },
        )
        self.assertEqual(code, 200)
        proposal = response["result"]["structuredContent"]
        self.assertEqual(proposal["status"], "approval_required")
        self.assertEqual(proposal["preview"]["details"]["name"], before["name"])
        after = self.document(client, "ai")
        self.assertEqual(
            (after["status"], after["docstatus"], after["modified"]),
            (before["status"], before["docstatus"], before["modified"]),
        )

        query = urlencode({"proposal_id": proposal["proposal_id"]})
        code, response = client.send(
            f"/api/method/platform_core.api.ai.get_proposal?{query}"
        )
        self.assertEqual(code, 200, response.get("exc_type"))
        approval = {
            "proposal_id": proposal["proposal_id"],
            "digest": response["message"]["digest"],
        }
        endpoint = "/api/method/platform_core.api.ai.approve_proposal"
        self.assertEqual(client.send(endpoint, approval)[0], 403)
        self.assertEqual(self.document(client, "ai")["modified"], before["modified"])

        code, response = client.send(endpoint, approval, csrf_token=client.csrf_token())
        self.assertEqual(code, 200, response.get("exc_type"))
        self.assertTrue(
            response["message"]["executed"], response["message"].get("deny_reason")
        )
        doc = self.document(client, "ai")
        self.assertEqual((doc["status"], doc["docstatus"]), ("Approved", 1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--with-ai", action="store_true")
    args = parser.parse_args()
    parsed_url = urlsplit(args.url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in {
        "127.0.0.1",
        "localhost",
    }:
        parser.error("The Frappe HTTP server must be on loopback.")
    LeaveHttpTest.base = args.url.rstrip("/")
    LeaveHttpTest.site = args.site
    LeaveHttpTest.data = json.loads(args.manifest.read_text())
    LeaveHttpTest.password = os.environ["CRONHR_TEST_PASSWORD"]
    LeaveHttpTest.with_ai = args.with_ai
    unittest.main(argv=[__file__], verbosity=2)
