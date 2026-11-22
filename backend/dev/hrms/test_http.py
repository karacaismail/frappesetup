"""Run HRMS TR checks against a seeded, isolated Frappe HTTP server."""

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
HRMS_LEAVE = "/api/method/hrms.hr.doctype.leave_application.leave_application"
AI_PATH = "/api/method/platform_core.api.ai"


class Client:
    def __init__(self, case, user, *, password=None):
        self.base = case.base
        self.site = case.site
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        status, _ = self.send(
            "/api/method/login", {"usr": user, "pwd": password or case.password}
        )
        case.assertEqual(status, 200, f"Synthetic login failed for {user}")

    def page(self, path):
        request = Request(self.base + path, headers={"X-Frappe-Site-Name": self.site})
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, response.read()
        except HTTPError as error:
            with error:
                return error.code, error.read()

    def csrf_token(self):
        status, body = self.page("/panel")
        match = re.search(
            rb'(?:frappe\.csrf_token\s*=|["]csrf_token["]\s*:)\s*"([^"]+)"', body
        )
        if status != 200 or match is None or match[1] in (b"None", b"null"):
            raise AssertionError(
                f"The portal did not provide a CSRF token (HTTP {status})."
            )
        return match[1].decode()

    def send(self, path, data=None, csrf_token=None, *, method=None):
        headers = {"Accept": "application/json", "X-Frappe-Site-Name": self.site}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if csrf_token:
            headers["X-Frappe-CSRF-Token"] = csrf_token
        request = Request(
            self.base + path,
            json.dumps(data).encode() if data is not None else None,
            headers,
            method=method,
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

    def leave_path(self, key):
        return f"{LEAVE_PATH}/{quote(self.data['leaves'][key], safe='')}"

    def document(self, client, key, status=200):
        code, result = client.send(self.leave_path(key))
        self.assertEqual(code, status, result.get("exc_type"))
        return result.get("data")

    def listed(self, client):
        query = urlencode({"fields": json.dumps(["name"]), "limit_page_length": 100})
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exc_type"))
        return {row["name"] for row in result["data"]}

    def leaves_owned_by(self, *actors):
        return {
            name
            for key, name in self.data["leaves"].items()
            if self.data["leave_owners"][key] in actors
        }

    def test_hrms_tr_roles_do_not_grant_desk_access(self):
        for actor in ("employee", "manager", "hr"):
            with self.subTest(actor=actor):
                client = self.login(actor)
                for path in ("/app", "/desk"):
                    with self.subTest(path=path):
                        code, _ = client.page(path)
                        self.assertEqual(code, 403)

    def test_employee_sees_only_own_leave_and_no_balance(self):
        client = self.login("employee")
        self.assertEqual(
            self.listed(client),
            self.leaves_owned_by("employee"),
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
                "/api/method/hrms_tr.api.approve_leave",
                {"name": self.data["leaves"]["employee"]},
            )[0],
            403,
        )

    def test_z_employee_can_create_draft_with_team_approver(self):
        client = self.login("employee")
        own = self.document(client, "employee")
        status, result = client.send(
            f"{HRMS_LEAVE}.get_leave_approver?{urlencode({'employee': own['employee']})}"
        )
        self.assertEqual(status, 200, result.get("exception"))
        self.assertEqual(result.get("message"), self.data["users"]["manager"])
        self.assertEqual(self.login("manager").page("/app")[0], 403)
        day = (date.fromisoformat(own["from_date"]) + timedelta(days=8)).isoformat()
        draft = {key: own[key] for key in ("employee", "company", "leave_type")}
        draft.update(
            leave_type=self.data["allocated_leave_type"],
            from_date=day,
            to_date=day,
            status="Open",
            leave_approver=self.data["users"]["manager"],
        )
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        settings_path = "/api/resource/HR%20Settings/HR%20Settings"
        mandatory = "leave_approver_mandatory_in_leave_application"
        code, result = admin.send(settings_path, {mandatory: 1}, method="PUT")
        self.assertEqual(code, 200, result.get("exception"))
        try:
            code, result = client.send(LEAVE_PATH, draft)
            self.assertEqual(code, 200, result.get("exception"))
            created = result["data"]
            self.assertEqual(created["leave_approver"], self.data["users"]["manager"])
            self.assertNotIn("leave_balance", created)
            path = f"{LEAVE_PATH}/{quote(created['name'], safe='')}"
            status, updated = client.send(
                path, {"description": "Updated synthetic request"}, method="PUT"
            )
            self.assertEqual(status, 200, updated.get("exception"))
            self.assertNotIn("leave_balance", updated["data"])
        finally:
            code, result = admin.send(settings_path, {mandatory: 0}, method="PUT")
            self.assertEqual(code, 200, result.get("exception"))

    def test_manager_can_only_approve_team_leave(self):
        client = self.login("manager")
        self.assertEqual(
            self.listed(client),
            self.leaves_owned_by("employee", "manager"),
        )
        self.assertEqual(self.document(client, "employee")["leave_balance"], 7)
        self.document(client, "outsider", 403)
        endpoint = "/api/method/hrms_tr.api.approve_leave"
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

    def test_sensitive_balance_read_paths(self):
        client = self.login("employee")
        for prefix in (LEAVE_PATH, "/api/v2/document/Leave%20Application"):
            with self.subTest(prefix=prefix):
                query = urlencode({"fields": json.dumps(["*"])})
                code, payload = client.send(f"{prefix}?{query}")
                self.assertEqual(code, 200, payload.get("exception"))
                self.assertTrue(payload["data"])
                self.assertTrue(
                    all("leave_balance" not in row for row in payload["data"])
                )

        name = quote(self.data["leaves"]["employee"], safe="")
        code, payload = client.send(f"/api/v2/document/Leave%20Application/{name}")
        self.assertEqual(code, 200, payload.get("exception"))
        self.assertNotIn("leave_balance", payload["data"])

        for arguments in (
            {"fields": json.dumps(["name"]), "order_by": "leave_balance"},
            {"fields": json.dumps(["sum(leave_balance) as balance_total"])},
            {"fields": json.dumps(["name"]), "group_by": "leave_balance"},
        ):
            with self.subTest(arguments=arguments):
                code, payload = client.send(f"{LEAVE_PATH}?{urlencode(arguments)}")
                self.assertIn(code, (403, 417), payload.get("exception"))

        args = urlencode(
            {
                "doctype": "Leave Application",
                "fieldname": "leave_balance",
                "filters": self.data["leaves"]["employee"],
            }
        )
        code, payload = client.send(f"/api/method/frappe.client.get_value?{args}")
        self.assertIn(code, (200, 403, 417), payload.get("exception"))
        if code == 200:
            self.assertFalse(payload.get("message"))

    def test_native_self_approval_and_employee_reassignment_are_denied(self):
        for actor in ("manager", "hr"):
            client = self.login(actor)
            own = self.document(client, actor)
            payload = {**own, "status": "Approved", "docstatus": 1}
            for endpoint, body, method in (
                (self.leave_path(actor), {"status": "Approved", "docstatus": 1}, "PUT"),
                ("/api/method/frappe.client.submit", {"doc": payload}, "POST"),
                (
                    "/api/method/frappe.desk.form.save.savedocs",
                    {"doc": json.dumps(payload), "action": "Submit"},
                    "POST",
                ),
            ):
                with self.subTest(actor=actor, endpoint=endpoint):
                    status, result = client.send(endpoint, body, method=method)
                    self.assertEqual(status, 403, result.get("exception"))
                    self.assertEqual(self.document(client, actor)["docstatus"], 0)
            status, result = client.send(
                self.leave_path(actor),
                {"employee": self.data["employees"]["employee"]},
                method="PUT",
            )
            self.assertIn(status, (403, 417), result.get("exception"))
            self.assertEqual(self.document(client, actor)["employee"], own["employee"])

    def test_hr_manages_approval_cancellation_and_amendment(self):
        hr = self.login("hr")
        manager = self.login("manager")
        approve = "/api/method/hrms_tr.api.approve_leave"
        name = self.data["leaves"]["hr_approve"]
        approved = hr.send(approve, {"name": name})
        self.assertEqual(approved[0], 200, approved[1].get("exception"))
        self.assertEqual(hr.send(approve, {"name": self.data["leaves"]["hr"]})[0], 403)
        cancel = "/api/method/frappe.client.cancel"
        args = {"doctype": "Leave Application", "name": name}
        status, result = manager.send(cancel, args)
        self.assertEqual(status, 403, result.get("exception"))
        status, result = hr.send(cancel, args)
        self.assertEqual(status, 200, result.get("exception"))
        old = self.document(hr, "hr_approve")
        self.assertEqual(old["docstatus"], 2)
        amendment = {
            key: old[key]
            for key in ("employee", "company", "leave_type", "from_date", "to_date")
        }
        amendment.update(amended_from=name, status="Open")
        status, result = self.login("outsider").send(LEAVE_PATH, amendment)
        self.assertIn(status, (403, 417), result.get("exception"))
        status, result = hr.send(LEAVE_PATH, amendment)
        self.assertEqual(status, 200, result.get("exception"))
        self.assertEqual(result["data"]["amended_from"], name)

    def test_leave_sharing_is_denied(self):
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        status, result = admin.send(
            "/api/method/frappe.share.add",
            {
                "doctype": "Leave Application",
                "name": self.data["leaves"]["outsider"],
                "user": self.data["users"]["employee"],
            },
        )
        self.assertEqual(status, 403, result.get("exception"))
        self.document(self.login("employee"), "outsider", 403)

    def test_missing_access_rules_close_list_and_document(self):
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        client = self.login("employee")
        path = "/api/resource/Access%20Rule"
        query = urlencode(
            {
                "filters": json.dumps(
                    {"document_type": "Leave Application", "is_active": 1}
                )
            }
        )
        status, payload = admin.send(f"{path}?{query}")
        self.assertEqual(status, 200, payload.get("exception"))
        names = [row["name"] for row in payload["data"]]
        self.assertEqual(len(names), 3)
        self.assertTrue(all(name.startswith("HRMS TR ") for name in names))
        changed = []
        self.assertTrue(self.listed(client))
        try:
            for name in names:
                endpoint = f"{path}/{quote(name, safe='')}"
                status, payload = admin.send(endpoint, {"is_active": 0}, method="PUT")
                self.assertEqual(status, 200, payload.get("exception"))
                changed.append(endpoint)
            self.assertEqual(self.listed(client), set())
            self.document(client, "employee", 403)
        finally:
            for endpoint in changed:
                status, payload = admin.send(endpoint, {"is_active": 1}, method="PUT")
                self.assertEqual(status, 200, payload.get("exception"))

    def test_legacy_hrms_balance_and_calendar_endpoints_are_closed(self):
        client = self.login("employee")
        today = date.today().isoformat()
        for actor in ("employee", "outsider"):
            for method, args in (
                ("get_leave_details", {}),
                (
                    "get_leave_balance_on",
                    {"leave_type": self.data["allocated_leave_type"]},
                ),
            ):
                with self.subTest(method=method, actor=actor):
                    arguments = {
                        "employee": self.data["employees"][actor],
                        "date": today,
                        **args,
                    }
                    code, result = client.send(
                        f"{HRMS_LEAVE}.{method}?{urlencode(arguments)}"
                    )
                    self.assertEqual(code, 403, result.get("exception"))
        for endpoint in (
            "/api/method/hrms.api.get_leave_balance_map",
            f"{HRMS_LEAVE}.get_events?{urlencode({'start': today, 'end': today, 'filters': '[]'})}",
        ):
            with self.subTest(endpoint=endpoint):
                code, result = client.send(endpoint)
                self.assertEqual(code, 403, result.get("exception"))

    def ai_call(self, client, name, version):
        return client.send(
            f"{AI_PATH}.mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "hrms_tr_approve_leave",
                    "arguments": {"name": name, "version": version},
                },
            },
        )

    def ai_propose(self, client, document):
        code, response = self.ai_call(client, document["name"], document["modified"])
        self.assertEqual(code, 200, response)
        proposal = response["result"]["structuredContent"]
        self.assertEqual(proposal["status"], "approval_required")
        self.assertEqual(proposal["preview"]["details"]["name"], document["name"])
        return proposal

    def ai_approval(self, client, proposal):
        query = urlencode({"proposal_id": proposal["proposal_id"]})
        code, response = client.send(f"{AI_PATH}.get_proposal?{query}")
        self.assertEqual(code, 200, response.get("exc_type"))
        return {
            "proposal_id": proposal["proposal_id"],
            "digest": response["message"]["digest"],
        }

    def test_ai_cannot_propose_approval_outside_actor_scope(self):
        if not self.with_ai:
            self.skipTest("Platform Core AI pending merge")
        hr = self.login("hr")
        for actor, key in (
            ("employee", "employee"),
            ("manager", "outsider"),
            ("manager", "manager"),
        ):
            with self.subTest(actor=actor, key=key):
                before = self.document(hr, key)
                code, response = self.ai_call(
                    self.login(actor), before["name"], before["modified"]
                )
                if code == 200:
                    result = response.get("result", {})
                    self.assertTrue(
                        "error" in response or result.get("isError"), response
                    )
                else:
                    self.assertIn(code, (403, 404, 417), response)
                after = self.document(hr, key)
                self.assertEqual(after["docstatus"], 0)
                self.assertEqual(after["modified"], before["modified"])

    def test_ai_rejects_approval_after_document_changes(self):
        if not self.with_ai:
            self.skipTest("Platform Core AI pending merge")
        manager = self.login("manager")
        employee = self.login("employee")
        before = self.document(manager, "ai_stale")
        proposal = self.ai_propose(manager, before)
        code, result = employee.send(
            self.leave_path("ai_stale"),
            {"description": "Updated after preview"},
            method="PUT",
        )
        self.assertEqual(code, 200, result.get("exception"))
        approval = self.ai_approval(manager, proposal)
        code, result = manager.send(
            f"{AI_PATH}.approve_proposal", approval, csrf_token=manager.csrf_token()
        )
        self.assertEqual(code, 200, result.get("exception"))
        self.assertFalse(result["message"]["executed"])
        self.assertEqual(result["message"]["deny_reason"], "document_changed")
        self.assertEqual(self.document(manager, "ai_stale")["docstatus"], 0)

    def test_ai_tool_writes_only_after_human_approval(self):
        if not self.with_ai:
            self.skipTest("Platform Core AI pending merge")
        client = self.login("manager")
        before = self.document(client, "ai")
        proposal = self.ai_propose(client, before)
        after = self.document(client, "ai")
        self.assertEqual(
            (after["status"], after["docstatus"], after["modified"]),
            (before["status"], before["docstatus"], before["modified"]),
        )

        approval = self.ai_approval(client, proposal)
        endpoint = f"{AI_PATH}.approve_proposal"
        csrf = client.csrf_token()
        self.assertEqual(client.send(endpoint, approval)[0], 403)
        self.assertEqual(self.document(client, "ai")["modified"], before["modified"])

        code, response = client.send(endpoint, approval, csrf_token=csrf)
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
    LeaveHttpTest.password = os.environ["HRMS_TR_TEST_PASSWORD"]
    LeaveHttpTest.with_ai = args.with_ai
    unittest.main(argv=[__file__], verbosity=2)
