"""Run HRMS TR checks against a seeded, isolated Frappe HTTP server."""

import argparse
import json
import os
import re
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from http.cookiejar import CookieJar
from math import ceil
from pathlib import Path
from threading import Barrier
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID

LEAVE_PATH = "/api/resource/Leave%20Application"
HRMS_LEAVE = "/api/method/hrms.hr.doctype.leave_application.leave_application"
AI_PATH = "/api/method/platform_core.api.ai"


class Client:
    def __init__(self, case, user, *, password=None):
        self.base = case.base
        self.site = case.site
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        if user is not None:
            status, _ = self.send("/api/method/login", {"usr": user, "pwd": password or case.password})
            case.assertEqual(status, 200, f"Synthetic login failed for {user}")

    def page(self, path):
        request = Request(self.base + path, headers={"X-Frappe-Site-Name": self.site})
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, response.read()
        except HTTPError as error:
            with error:
                return error.code, error.read()

    def final_path(self, path):
        """Path of the page the redirects end on."""
        request = Request(self.base + path, headers={"X-Frappe-Site-Name": self.site})
        try:
            with self.opener.open(request, timeout=15) as response:
                return urlsplit(response.geturl()).path
        except HTTPError as error:
            with error:
                return urlsplit(error.geturl()).path

    def csrf_token(self):
        status, body = self.page("/panel")
        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', body)
        match = match or re.search(rb'(?:frappe\.csrf_token\s*=|["]csrf_token["]\s*:)\s*"([^"]+)"', body)
        if status != 200 or match is None or match[1] in (b"None", b"null"):
            raise AssertionError(f"The portal did not provide a CSRF token (HTTP {status}).")
        return match[1].decode()

    def send(self, path, data=None, csrf_token=None, *, method=None, authorization=None):
        headers = {"Accept": "application/json", "X-Frappe-Site-Name": self.site}
        if authorization:
            headers["Authorization"] = authorization
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
        if status == 200:
            self.contract_validators["detail"].validate(result)
        return result.get("data")

    def listed(self, client):
        query = urlencode({"fields": json.dumps(["name", "employee"]), "limit_page_length": 100})
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exc_type"))
        self.contract_validators["list"].validate(result)
        return {row["name"]: row["employee"] for row in result["data"]}

    def leave_ledger_entries(self, client, name):
        query = urlencode(
            {
                "filters": json.dumps({"transaction_type": "Leave Application", "transaction_name": name}),
                "fields": json.dumps(["name"]),
                "limit_page_length": 100,
            }
        )
        code, result = client.send(f"/api/resource/Leave%20Ledger%20Entry?{query}")
        self.assertEqual(code, 200, result.get("exc_type"))
        return result["data"]

    def assert_list_scope(self, client, *actors):
        records = self.listed(client)
        self.assertTrue(self.leaves_owned_by(*actors) <= records.keys())
        allowed = {self.data["employees"][actor] for actor in actors}
        self.assertLessEqual(set(records.values()), allowed)

    def leaves_owned_by(self, *actors):
        return {name for key, name in self.data["leaves"].items() if self.data["leave_owners"][key] in actors}

    def simultaneous_posts(self, path, requests):
        start = Barrier(len(requests))

        def post(request):
            client, body = request
            start.wait(timeout=20)
            started = perf_counter()
            try:
                status, payload = client.send(path, body)
            except (URLError, TimeoutError) as error:
                status, payload = 0, {"exc_type": type(error).__name__}
            return status, payload, (perf_counter() - started) * 1_000

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            return list(pool.map(post, requests))

    def test_concurrent_approvals_and_cancellations_keep_one_result(self):
        hr = self.login("hr")
        other_hr = Client(self, self.data["concurrency"]["reviewer"])
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        initial = self.document(hr, "concurrent")
        name = initial["name"]
        self.assertEqual(self.leave_ledger_entries(admin, name), [])
        key = {field: initial[field] for field in ("employee", "from_date", "to_date")}
        query = urlencode({"filters": json.dumps(key)})

        for action, expected_docstatus, ledger_count in (
            ("approve", 1, 1),
            ("cancel", 2, 0),
        ):
            with self.subTest(action=action):
                body = self.approval_payload(self.document(hr, "concurrent"))
                results = self.simultaneous_posts(
                    f"/api/method/hrms_tr.api.{action}_leave",
                    [(hr, body), (other_hr, body)],
                )
                outcomes = sorted((status, payload.get("exc_type", "")) for status, payload, _ in results)
                print(f"Concurrency {action}: {outcomes}")
                self.assertEqual(outcomes, [(200, ""), (417, "TimestampMismatchError")])
                for status, payload, _ in results:
                    if status == 200:
                        self.assertEqual(payload["message"], {"name": name})
                self.assertEqual(self.document(hr, "concurrent")["docstatus"], expected_docstatus)
                self.assertEqual(len(self.leave_ledger_entries(admin, name)), ledger_count)
                status, listed = hr.send(f"{LEAVE_PATH}?{query}")
                self.assertEqual(status, 200, listed.get("exc_type"))
                self.assertEqual(listed["data"], [{"name": name}])

    def test_concurrent_employee_requests_have_no_lost_or_duplicate_records(self):
        scenario = self.data["concurrency"]
        actors = scenario["employees"]
        self.assertEqual(len(actors), 20)
        hr = self.login("hr")
        template = self.document(hr, "employee")
        employees = [self.data["employees"][actor] for actor in actors]
        requests = [
            (
                self.login(actor),
                {
                    "employee": employee,
                    "company": template["company"],
                    "leave_type": template["leave_type"],
                    "from_date": scenario["request_day"],
                    "to_date": scenario["request_day"],
                    "status": "Open",
                },
            )
            for actor, employee in zip(actors, employees, strict=True)
        ]
        results = self.simultaneous_posts(LEAVE_PATH, requests)
        errors = Counter((status, payload.get("exc_type")) for status, payload, _ in results if status != 200)
        sample_count = len(results)
        p95 = sorted(elapsed for _, _, elapsed in results)[ceil(sample_count * 0.95) - 1]
        error_count = sum(errors.values())
        print(
            f"Concurrency employees: requests={sample_count} errors={error_count} "
            f"error_rate={error_count / sample_count:.0%} p95_ms={p95:.2f} details={dict(errors)}"
        )
        self.assertEqual(errors, {})
        expected = {
            payload["data"]["name"]: employee
            for employee, (_, payload, _) in zip(employees, results, strict=True)
        }
        self.assertEqual(len(expected), sample_count)
        self.assertTrue(all(UUID(name).version == 7 for name in expected))
        query = urlencode(
            {
                "fields": json.dumps(["name", "employee"]),
                "filters": json.dumps(
                    {
                        "employee": ["in", employees],
                        "from_date": scenario["request_day"],
                    }
                ),
                "limit_page_length": 100,
            }
        )
        status, payload = hr.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(status, 200, payload.get("exc_type"))
        self.assertEqual({row["name"]: row["employee"] for row in payload["data"]}, expected)

    def test_d6_http_permission_matrix(self):
        fixture = self.data["d6"]
        actors = {
            "guest": Client(self, None),
            "roleless": Client(self, fixture["roleless"]),
            "foreign": Client(self, fixture["foreign"]),
            "authorized": self.login("hr"),
        }
        hr = actors["authorized"]
        self.document(actors["foreign"], "foreign")
        draft = self.document(hr, "d6")
        list_query = urlencode({"filters": json.dumps({"name": draft["name"]})})
        detail = self.leave_path("d6")
        approver = "/api/method/hrms_tr.api.get_leave_approver"
        closed = "/api/method/hrms_tr.hrms_endpoints.deny_legacy_leave_query"
        attendance = quote(fixture["attendance"], safe="")
        warnings = f"/api/v2/document/Attendance%20Request/{attendance}/method/get_attendance_warnings/"

        for actor, client in actors.items():
            allowed = actor == "authorized"
            with self.subTest(endpoint="list", actor=actor):
                status, payload = client.send(f"{LEAVE_PATH}?{list_query}")
                if allowed:
                    self.assertEqual(status, 200, payload.get("exc_type"))
                    self.assertEqual(payload["data"], [{"name": draft["name"]}])
                else:
                    self.assertIn(status, (200, 403), payload.get("exc_type"))
                    if status == 200:
                        self.assertEqual(payload["data"], [])
                outcome = f"{status} empty" if status == 200 and not payload["data"] else str(status)
                print(f"D-6 list {actor}: {outcome}")

            employee = fixture["roleless_employee"] if actor == "roleless" else draft["employee"]
            approver_query = urlencode({"employee": employee})
            scenarios = (
                ("detail", "GET", detail, 200 if allowed else 403),
                (
                    "approver",
                    "GET",
                    f"{approver}?{approver_query}",
                    200 if allowed else 403,
                ),
                ("closed GET", "GET", closed, 403),
                ("closed POST", "POST", closed, 403),
                ("attendance GET", "GET", warnings, 403),
                ("attendance POST", "POST", warnings, 403),
            )
            for endpoint, method, path, expected in scenarios:
                self.check_d6_response(actor, client, endpoint, method, path, expected)

        for action, before, final_status in (("approve", 0, 1), ("cancel", 1, 2)):
            initial = self.document(hr, "d6")
            self.assertEqual(initial["docstatus"], before)
            for actor, client in actors.items():
                self.check_d6_response(
                    actor,
                    client,
                    action,
                    "POST",
                    f"/api/method/hrms_tr.api.{action}_leave",
                    200 if actor == "authorized" else 403,
                    body=self.approval_payload(initial),
                )
                current = self.document(hr, "d6")
                if actor == "authorized":
                    self.assertEqual(current["docstatus"], final_status)
                else:
                    self.assertEqual(current, initial)

    def check_d6_response(self, actor, client, endpoint, method, path, expected, *, body=None):
        with self.subTest(endpoint=endpoint, actor=actor):
            status, payload = client.send(path, body, method=method)
            print(f"D-6 {endpoint} {actor}: {status}")
            self.assertEqual(status, expected, payload.get("exc_type"))
            if expected == 403:
                error_type = (
                    payload["errors"][0]["type"] if path.startswith("/api/v2/") else payload.get("exc_type")
                )
                self.assertEqual(error_type, "PermissionError")

    def test_native_leave_list_projection_filters_and_pagination(self):
        client = self.login("employee")
        names = sorted(self.leaves_owned_by("employee"))[:2]
        filters = json.dumps([["name", "in", names]])
        query = urlencode({"filters": filters, "order_by": "name asc", "limit_page_length": 1})
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exception"))
        self.contract_validators["list"].validate(result)
        self.assertEqual(result["data"], [{"name": names[0]}])

        query = urlencode(
            {
                "fields": json.dumps(["name", "employee"]),
                "filters": filters,
                "order_by": "name asc",
                "limit_start": 1,
                "limit_page_length": 1,
            }
        )
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exception"))
        self.contract_validators["list"].validate(result)
        self.assertEqual(
            result["data"],
            [{"name": names[1], "employee": self.data["employees"]["employee"]}],
        )

        query = urlencode(
            {
                "fields": json.dumps(["name", "modified"]),
                "filters": filters,
                "order_by": "modified desc, name asc",
            }
        )
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exc_type"))
        self.contract_validators["list"].validate(result)
        rows = result["data"]
        self.assertEqual(sorted(row["name"] for row in rows), names)
        self.assertEqual(
            rows,
            sorted(
                sorted(rows, key=lambda row: row["name"]),
                key=lambda row: row["modified"],
                reverse=True,
            ),
        )

        query = urlencode({"filters": json.dumps({"employee": self.data["employees"]["outsider"]})})
        code, result = client.send(f"{LEAVE_PATH}?{query}")
        self.assertEqual(code, 200, result.get("exception"))
        self.contract_validators["list"].validate(result)
        self.assertEqual(result["data"], [])
        code, _ = Client(self, None).send(LEAVE_PATH)
        self.assertEqual(code, 403)

    def test_hrms_tr_roles_do_not_grant_desk_access(self):
        for actor in ("employee", "manager", "hr"):
            with self.subTest(actor=actor):
                client = self.login(actor)
                # G-53: Desk requests end on the panel. The bundled HRMS pages stay closed.
                for path in ("/app", "/desk"):
                    with self.subTest(path=path):
                        self.assertEqual(client.final_path(path), "/panel")
                for path in ("/hrms", "/hr/team", "/roster"):
                    with self.subTest(path=path):
                        code, _ = client.page(path)
                        self.assertEqual(code, 403)

    def test_employee_sees_only_own_leave_and_no_balance(self):
        client = self.login("employee")
        self.assert_list_scope(client, "employee")
        employee_draft = self.document(client, "employee")
        self.assertNotIn("leave_balance", employee_draft)
        query = urlencode({"fields": json.dumps(["name", "leave_balance"])})
        code, payload = client.send(f"{LEAVE_PATH}?{query}")
        self.assertIn(code, (200, 403, 417), payload.get("exc_type"))
        if code == 200:
            self.assertTrue(all("leave_balance" not in row for row in payload["data"]))
        self.document(client, "outsider", 403)
        self.assertEqual(
            client.send(
                "/api/method/hrms_tr.api.approve_leave",
                self.approval_payload(employee_draft),
            )[0],
            403,
        )

    def test_employee_can_create_draft_with_team_approver(self):
        client = self.login("employee")
        own = self.document(client, "employee")
        status, result = client.send(
            f"{HRMS_LEAVE}.get_leave_approver?{urlencode({'employee': own['employee']})}"
        )
        self.assertEqual(status, 403, result.get("exception"))
        lookup = "/api/method/hrms_tr.api.get_leave_approver"
        for invalid_query in ("", "?employee=", f"?employee={'x' * 141}"):
            with self.subTest(query=invalid_query):
                code, error = client.send(f"{lookup}{invalid_query}")
                self.assertEqual(code, 417, error.get("exc_type"))
        for actor in ("outsider", "guest"):
            with self.subTest(actor=actor):
                caller = self.login(actor) if actor != "guest" else Client(self, None)
                code, error = caller.send(f"{lookup}?{urlencode({'employee': own['employee']})}")
                self.assertEqual((code, error.get("exc_type")), (403, "PermissionError"))
        status, result = client.send(f"{lookup}?{urlencode({'employee': own['employee']})}")
        self.assertEqual(status, 200, result.get("exc_type"))
        self.contract_validators["approver"].validate(result)
        self.assertEqual(result["message"], {"approver": self.data["users"]["manager"]})
        self.assertEqual(self.login("manager").final_path("/app"), "/panel")
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
            status, updated = client.send(path, {"description": "Updated synthetic request"}, method="PUT")
            self.assertEqual(status, 200, updated.get("exception"))
            self.assertNotIn("leave_balance", updated["data"])
        finally:
            code, result = admin.send(settings_path, {mandatory: 0}, method="PUT")
            self.assertEqual(code, 200, result.get("exception"))

    def test_employee_and_manager_cannot_create_outside_their_permissions(self):
        source = self.document(self.login("employee"), "employee")
        day = (date.fromisoformat(source["from_date"]) + timedelta(days=12)).isoformat()
        for actor, employee in (("employee", "outsider"), ("manager", "employee")):
            with self.subTest(actor=actor):
                draft = {
                    "employee": self.data["employees"][employee],
                    "company": source["company"],
                    "leave_type": source["leave_type"],
                    "from_date": day,
                    "to_date": day,
                    "status": "Open",
                }
                code, result = self.login(actor).send(LEAVE_PATH, draft)
                self.assertEqual((code, result.get("exc_type")), (403, "PermissionError"))

    def test_hr_can_read_employee_records_with_read_only_permission(self):
        employee = self.data["employees"]["outsider"]
        path = f"/api/resource/Employee/{quote(employee, safe='')}"
        hr = self.login("hr")
        code, result = hr.send(path)
        self.assertEqual(code, 200, result.get("exc_type"))
        self.assertEqual(result["data"]["name"], employee)
        code, result = hr.send(path, {"first_name": "Unauthorized synthetic update"}, method="PUT")
        self.assertEqual((code, result.get("exc_type")), (403, "PermissionError"))
        for actor in ("manager", "employee"):
            with self.subTest(actor=actor):
                code, result = self.login(actor).send(path)
                self.assertEqual((code, result.get("exc_type")), (403, "PermissionError"))

    def test_manager_cannot_edit_team_leave_details(self):
        manager = self.login("manager")
        before = self.document(manager, "manager_edit")
        day = (date.fromisoformat(before["to_date"]) + timedelta(days=1)).isoformat()
        for changes in (
            {"from_date": day, "to_date": day},
            {"leave_type": self.data["allocated_leave_type"]},
            {"description": "Unauthorized manager edit"},
            {"owner": self.data["users"]["manager"]},
        ):
            with self.subTest(changes=changes):
                code, result = manager.send(self.leave_path("manager_edit"), changes, method="PUT")
                self.assertEqual((code, result.get("exc_type")), (403, "PermissionError"))
                after = self.document(manager, "manager_edit")
                for field in (*changes, "modified"):
                    self.assertEqual(after.get(field), before.get(field), field)

    @staticmethod
    def approval_payload(document):
        return {"name": document["name"], "version": document["modified"]}

    def test_manager_can_only_approve_team_leave(self):
        client = self.login("manager")
        self.assert_list_scope(client, "employee", "manager")
        self.assertEqual(self.document(client, "employee")["leave_balance"], 7)
        self.document(client, "outsider", 403)
        endpoint = "/api/method/hrms_tr.api.approve_leave"
        outsider = self.document(self.login("hr"), "outsider")
        self.assertEqual(client.send(endpoint, self.approval_payload(outsider))[0], 403)
        own = self.document(client, "manager")
        self.assertEqual(client.send(endpoint, self.approval_payload(own))[0], 403)

        before = self.document(client, "manager_approve")
        code, result = self.login("employee").send(
            self.leave_path("manager_approve"),
            {"description": "Updated after the manager reviewed the request"},
            method="PUT",
        )
        self.assertEqual(code, 200, result.get("exception"))
        changed = self.document(client, "manager_approve")
        self.assertNotEqual(changed["modified"], before["modified"])
        code, result = client.send(endpoint, self.approval_payload(before))
        self.assertEqual(code, 417, result.get("exception"))
        self.assertEqual(result.get("exc_type"), "TimestampMismatchError")
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        persisted = self.document(admin, "manager_approve")
        for field in ("modified", "status", "docstatus"):
            self.assertEqual(persisted[field], changed[field], field)
        self.assertEqual(self.leave_ledger_entries(admin, persisted["name"]), [])

        code, result = client.send(endpoint, self.approval_payload(changed))
        self.assertEqual(code, 200, result.get("exc_type"))
        doc = self.document(client, "manager_approve")
        self.assertEqual((doc["status"], doc["docstatus"]), ("Approved", 1))

    def test_hr_can_read_all_leaves(self):
        client = self.login("hr")
        self.assert_list_scope(client, *self.data["employees"])
        self.assertEqual(self.document(client, "outsider")["leave_balance"], 7)

    def test_legacy_roles_do_not_grant_leave_access(self):
        for role in ("HR User", "Leave Approver", "Employee"):
            user = self.data["legacy_users"][role]
            with self.subTest(role=role):
                client = Client(self, user)
                status, result = client.send(LEAVE_PATH)
                self.assertIn(status, (200, 403), result.get("exception"))
                if status == 200:
                    self.assertEqual(result["data"], [])
                self.document(client, "employee", 403)

    def test_operations_roles_can_read_write_submit_and_cancel(self):
        for role, key in (
            ("System Manager", "system_manager_approve"),
            ("HR Manager", "hr_manager_approve"),
        ):
            with self.subTest(role=role):
                client = Client(self, self.data["legacy_users"][role])
                self.assert_list_scope(client, *self.data["employees"])
                initial = self.document(client, key)
                self.assertEqual(initial["status"], "Open")
                self.assertEqual(initial["docstatus"], 0)
                description = "Reviewed by a synthetic operations user"
                code, result = client.send(self.leave_path(key), {"description": description}, method="PUT")
                self.assertEqual(code, 200, result.get("exception"))
                self.assertEqual(result["data"]["description"], description)

                draft = {**result["data"], "status": "Approved"}
                code, result = client.send("/api/method/frappe.client.submit", {"doc": draft})
                self.assertEqual(code, 200, result.get("exception"))
                approved = self.document(client, key)
                self.assertEqual(approved["status"], "Approved")
                self.assertEqual(approved["docstatus"], 1)

                code, result = client.send(
                    "/api/method/frappe.client.cancel",
                    {"doctype": "Leave Application", "name": initial["name"]},
                )
                self.assertEqual(code, 200, result.get("exception"))
                self.assertEqual(self.document(client, key)["docstatus"], 2)

    def test_sensitive_balance_read_paths(self):
        client = self.login("employee")
        for prefix in (LEAVE_PATH, "/api/v2/document/Leave%20Application"):
            with self.subTest(prefix=prefix):
                query = urlencode({"fields": json.dumps(["*"])})
                code, payload = client.send(f"{prefix}?{query}")
                self.assertEqual(code, 200, payload.get("exception"))
                self.assertTrue(payload["data"])
                self.assertTrue(all("leave_balance" not in row for row in payload["data"]))

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
                if "balance_total" in arguments.get("fields", "") and code == 200:
                    self.assertTrue(payload["data"])
                    self.assertTrue(all(set(row) == {"name"} for row in payload["data"]))
                else:
                    self.assertIn(code, (403, 417), payload.get("exception"))

        for option in ("filters", "or_filters"):
            with self.subTest(option=option):
                query = urlencode({option: json.dumps({"leave_balance": [">", 5]})})
                code, payload = client.send(f"{LEAVE_PATH}?{query}")
                print(f"\nLeave balance {option}: HTTP {code}", flush=True)
                self.assertIn(code, (200, 403, 417), payload.get("exc_type"))
                if code == 200:
                    self.assertEqual(payload["data"], [])

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
            self.assertLessEqual(set(payload.get("message") or {}), {"name"})

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
        target = self.document(hr, "hr_approve")
        name = target["name"]
        approved = hr.send(approve, self.approval_payload(target))
        self.assertEqual(approved[0], 200, approved[1].get("exception"))
        own = self.document(hr, "hr")
        self.assertEqual(hr.send(approve, self.approval_payload(own))[0], 403)
        cancel = "/api/method/frappe.client.cancel"
        args = {"doctype": "Leave Application", "name": name}
        status, result = manager.send(cancel, args)
        self.assertEqual(status, 403, result.get("exception"))
        status, result = hr.send(cancel, args)
        self.assertEqual(status, 403, result.get("exception"))
        leave_path = self.leave_path("hr_approve")
        status, result = manager.send(leave_path, {"docstatus": 2}, method="PUT")
        self.assertEqual(status, 403, result.get("exception"))
        status, result = hr.send(leave_path, {"docstatus": 2}, method="PUT")
        self.assertEqual(status, 403, result.get("exception"))
        cancel = "/api/method/hrms_tr.api.cancel_leave"
        submitted = self.document(hr, "hr_approve")
        args = self.approval_payload(submitted)
        status, result = Client(self, None).send(cancel, args)
        self.assertEqual((status, result.get("exc_type")), (403, "PermissionError"))
        status, result = hr.send(f"{cancel}?{urlencode(args)}")
        self.assertEqual((status, result.get("exc_type")), (403, "PermissionError"))
        for actor in ("manager", "employee"):
            with self.subTest(actor=actor):
                status, result = self.login(actor).send(cancel, args)
                self.assertEqual((status, result.get("exc_type")), (403, "PermissionError"))
        for invalid_args in (
            {"name": name},
            {"version": args["version"]},
            {**args, "version": ""},
            {**args, "version": "x" * 41},
        ):
            with self.subTest(args=invalid_args):
                status, result = hr.send(cancel, invalid_args)
                self.assertEqual(status, 417, result.get("exc_type"))
        status, result = hr.send(cancel, self.approval_payload(target))
        self.assertEqual((status, result.get("exc_type")), (417, "TimestampMismatchError"))
        self.assertEqual(self.document(hr, "hr_approve")["modified"], submitted["modified"])
        status, result = hr.send(cancel, args)
        self.assertEqual(status, 200, result.get("exc_type"))
        self.contract_validators["cancel"].validate(result)
        self.assertEqual(result["message"], {"name": name})
        old = self.document(hr, "hr_approve")
        self.assertEqual(old["docstatus"], 2)
        amendment = {key: old[key] for key in ("employee", "company", "leave_type", "from_date", "to_date")}
        amendment.update(amended_from=name, status="Open")
        status, result = self.login("outsider").send(LEAVE_PATH, amendment)
        self.assertIn(status, (403, 417), result.get("exception"))
        status, result = hr.send(LEAVE_PATH, amendment)
        self.assertEqual(
            status,
            200,
            {key: result.get(key) for key in ("exc_type", "_server_messages")},
        )
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
        filters = urlencode(
            {
                "filters": json.dumps(
                    {
                        "share_doctype": "Leave Application",
                        "share_name": self.data["leaves"]["outsider"],
                    }
                )
            }
        )
        status, result = admin.send(f"/api/resource/DocShare?{filters}")
        self.assertEqual(status, 200, result.get("exception"))
        self.assertEqual(result["data"], [])
        self.document(self.login("employee"), "outsider", 403)

    def test_missing_access_rules_close_list_and_document(self):
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        client = self.login("employee")
        path = "/api/resource/PLT%20Access%20Rule"
        query = urlencode(
            {
                "filters": json.dumps({"document_type": "Leave Application", "is_active": 1}),
                "fields": json.dumps(["name", "role"]),
            }
        )
        status, payload = admin.send(f"{path}?{query}")
        self.assertEqual(status, 200, payload.get("exception"))
        names = [row["name"] for row in payload["data"]]
        self.assertEqual(
            {row["role"] for row in payload["data"]},
            {
                "HRT Employee",
                "HRT Manager",
                "HRT Admin",
                "System Manager",
                "HR Manager",
            },
        )
        self.assertEqual(len(names), 5)
        changed = []
        self.assertTrue(self.listed(client))
        try:
            for name in names:
                endpoint = f"{path}/{quote(name, safe='')}"
                status, payload = admin.send(endpoint, {"is_active": 0}, method="PUT")
                self.assertEqual(status, 200, payload.get("exception"))
                changed.append(endpoint)
            self.assertEqual(self.listed(client), {})
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
                (f"{HRMS_LEAVE}.get_leave_details", {}),
                (
                    f"{HRMS_LEAVE}.get_leave_balance_on",
                    {"leave_type": self.data["allocated_leave_type"]},
                ),
                ("/api/method/hrms.api.get_leave_types", {}),
            ):
                with self.subTest(method=method, actor=actor):
                    arguments = {
                        "employee": self.data["employees"][actor],
                        "date": today,
                        **args,
                    }
                    code, result = client.send(f"{method}?{urlencode(arguments)}")
                    self.assertEqual(code, 403, result.get("exception"))
        for endpoint in (
            "/api/method/hrms.api.get_leave_balance_map",
            f"{HRMS_LEAVE}.get_events?{urlencode({'start': today, 'end': today, 'filters': '[]'})}",
        ):
            with self.subTest(endpoint=endpoint):
                code, result = client.send(endpoint)
                self.assertEqual(code, 403, result.get("exception"))

    def test_website_user_can_approve_but_cannot_call_closed_methods(self):
        manager = self.login("manager")
        doc = self.document(manager, "website_approval")
        legacy = "hrms.hr.doctype.leave_application.leave_application.get_leave_details"
        replacement = "hrms_tr.hrms_endpoints.deny_legacy_leave_query"
        for method in (legacy, replacement):
            for path in (
                f"/api/method/{method}",
                f"/api/v1/method/{method}",
                f"/api/v2/method/{method}",
                f"/?{urlencode({'cmd': method})}",
            ):
                with self.subTest(path=path):
                    code, result = manager.send(path)
                    self.assertEqual(code, 403)
                    if path.startswith("/api/v2/"):
                        (error,) = result["errors"]
                        self.assertEqual(error["type"], "PermissionError")
                        messages = [error["message"]]
                    else:
                        self.assertEqual(result["exc_type"], "PermissionError")
                        messages = [
                            json.loads(message)["message"]
                            for message in json.loads(result["_server_messages"])
                        ]
                    self.assertIn("You are not permitted to call this method.", messages)

        code, result = manager.send("/api/method/hrms_tr.api.approve_leave", self.approval_payload(doc))
        self.assertEqual(code, 200, result.get("exc_type"))
        self.assertEqual(result["message"]["name"], doc["name"])
        approved = self.document(manager, "website_approval")
        self.assertEqual((approved["status"], approved["docstatus"]), ("Approved", 1))

    def test_guest_cannot_approve_or_call_legacy_replacement(self):
        guest = Client(self, None)
        outsider = self.document(self.login("hr"), "outsider")
        code, _ = guest.send("/api/method/hrms_tr.api.approve_leave", self.approval_payload(outsider))
        self.assertEqual(code, 403)
        code, _ = guest.send("/api/method/hrms_tr.hrms_endpoints.deny_legacy_leave_query")
        self.assertEqual(code, 403)
        code, _ = self.login("manager").send("/api/method/hrms_tr.hrms_endpoints.deny_legacy_leave_query")
        self.assertEqual(code, 403)

    def test_invalid_api_token_is_unauthorized(self):
        guest = Client(self, None)
        code, result = guest.send(LEAVE_PATH, authorization="token missing-test-key:missing-test-secret")
        self.assertEqual(code, 401, result.get("exc_type"))

    def test_approval_rejects_invalid_verb_version_and_client_role(self):
        manager = self.login("manager")
        employee = self.login("employee")
        endpoint = "/api/method/hrms_tr.api.approve_leave"
        before = self.document(manager, "employee")
        body = self.approval_payload(before)
        status, _ = manager.page(f"{endpoint}?{urlencode(body)}")
        self.assertIn(status, (403, 405))
        for invalid_body in (
            {"name": before["name"]},
            {"version": body["version"]},
            {**body, "version": ""},
            {**body, "version": "x" * 41},
            {**body, "version": ["not a version"]},
        ):
            with self.subTest(body=invalid_body):
                status, result = manager.send(endpoint, invalid_body)
                self.assertEqual(status, 417, result.get("exc_type"))
        status, _ = employee.send(endpoint, {**body, "role": "HRT Admin"})
        self.assertIn(status, (403, 417))
        self.assertEqual(self.document(manager, "employee"), before)

    def test_legacy_derived_leave_data_endpoints_are_closed(self):
        hr = Client(self, self.data["legacy_users"]["HR Manager"])
        for method, args in (
            (
                "hrms.payroll.doctype.salary_slip.salary_slip.make_salary_slip_from_timesheet",
                {"source_name": "SYNTHETIC-TIMESHEET"},
            ),
            (
                "hrms.payroll.doctype.salary_structure.salary_structure.make_salary_slip",
                {
                    "source_name": "SYNTHETIC-SALARY-STRUCTURE",
                    "employee": self.data["employees"]["employee"],
                },
            ),
        ):
            with self.subTest(method=method):
                status, result = hr.send(f"/api/method/{method}", args)
                self.assertEqual(status, 403, result.get("exception"))
                self.assertIn("Read leave information", result.get("exception", ""))

        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        day = (date.today() + timedelta(days=60)).isoformat()
        code, payload = admin.send(
            "/api/resource/Attendance%20Request",
            {
                "employee": self.data["employees"]["employee"],
                "from_date": day,
                "to_date": day,
                "reason": "Work From Home",
            },
        )
        self.assertEqual(code, 200, payload.get("exception"))
        name = quote(payload["data"]["name"], safe="")
        path = f"/api/v2/document/Attendance%20Request/{name}/method/get_attendance_warnings/"
        status, _ = admin.page(path)
        self.assertEqual(status, 403)

    def test_legacy_hrms_leave_reports_are_closed(self):
        client = Client(self, self.data["legacy_users"]["HR Manager"])
        today = date.today().isoformat()
        leave = self.document(client, "employee")
        filters = json.dumps(
            {
                "company": leave["company"],
                "employee": leave["employee"],
                "from_date": today,
                "to_date": today,
            }
        )
        for report in (
            "Employee Leave Balance Summary",
            "Employee Leave Balance",
            "Leave Ledger",
        ):
            status, _ = client.send(
                "/api/method/frappe.core.doctype.prepared_report.prepared_report.make_prepared_report",
                {"report_name": report, "filters": filters},
            )
            self.assertEqual(status, 403)
            for method in ("run", "export_query"):
                with self.subTest(report=report, method=method):
                    query = urlencode(
                        {
                            "report_name": report,
                            "filters": filters,
                            "file_format_type": "CSV",
                        }
                    )
                    status, _ = client.page(f"/api/method/frappe.desk.query_report.{method}?{query}")
                    self.assertEqual(status, 403)

    def test_stored_legacy_report_downloads_are_closed(self):
        admin = Client(self, "Administrator", password=os.environ["ADMIN_PASSWORD"])
        query = urlencode({"dn": self.data["prepared_report"]})
        path = "/api/method/frappe.core.doctype.prepared_report.prepared_report.download_attachment"
        status, _ = admin.page(f"{path}?{query}")
        self.assertEqual(status, 403)
        status, _ = admin.page(self.data["prepared_report_file"])
        self.assertEqual(status, 403)

    def ai_call(self, client, name):
        return client.send(
            f"{AI_PATH}.mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "hrt_approve_leave",
                    "arguments": {"name": name},
                },
            },
        )

    def ai_propose(self, client, document):
        code, response = self.ai_call(client, document["name"])
        self.assertEqual(code, 200, response)
        proposal = response["result"]["structuredContent"]
        self.assertEqual(proposal["status"], "approval_required")
        self.assertEqual(proposal["preview"]["details"], {"name": document["name"]})
        changes = proposal["preview"]["changes"]
        self.assertEqual(len(changes), 2)
        for change in changes:
            self.assertEqual(set(change), {"fieldname", "label", "old", "new"})
            self.assertIsInstance(change["label"], str)
            self.assertTrue(change["label"])
        transitions = {change["fieldname"]: (change["old"], change["new"]) for change in changes}
        self.assertEqual(transitions, {"status": ("Open", "Approved"), "docstatus": (0, 1)})
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
                code, response = self.ai_call(self.login(actor), before["name"])
                if code == 200:
                    result = response.get("result", {})
                    self.assertTrue("error" in response or result.get("isError"), response)
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
        changed = self.document(employee, "ai_stale")
        self.assertNotEqual(changed["modified"], before["modified"])
        approval = self.ai_approval(manager, proposal)
        code, result = manager.send(f"{AI_PATH}.approve_proposal", approval, csrf_token=manager.csrf_token())
        self.assertEqual(code, 200, result.get("exception"))
        self.assertFalse(result["message"]["executed"])
        self.assertEqual(result["message"]["deny_reason"], "document_changed")
        query = urlencode({"proposal_id": proposal["proposal_id"]})
        code, response = manager.send(f"{AI_PATH}.get_proposal?{query}")
        self.assertEqual(code, 200, response.get("exc_type"))
        self.assertEqual(response["message"]["status"], "rejected")
        persisted = self.document(manager, "ai_stale")
        self.assertEqual(persisted["docstatus"], 0)
        self.assertEqual(persisted["modified"], changed["modified"])

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
        code, response = client.send(endpoint, approval)
        self.assertEqual((code, response.get("exc_type")), (400, "CSRFTokenError"))
        self.assertEqual(self.document(client, "ai")["modified"], before["modified"])

        code, response = client.send(endpoint, approval, csrf_token=csrf)
        self.assertEqual(code, 200, response.get("exc_type"))
        self.assertTrue(response["message"]["executed"], response["message"].get("deny_reason"))
        doc = self.document(client, "ai")
        self.assertEqual((doc["status"], doc["docstatus"]), ("Approved", 1))


def load_contract_validators(path):
    import yaml
    from jsonschema import Draft202012Validator

    contract = yaml.safe_load(path.read_text())
    return {
        response: Draft202012Validator(
            {
                **contract,
                **contract["paths"][path][method]["responses"]["200"]["content"]["application/json"][
                    "schema"
                ],
            }
        )
        for response, path, method in (
            ("list", "/resource/Leave%20Application", "get"),
            ("detail", "/resource/Leave%20Application/{name}", "get"),
            ("approver", "/method/hrms_tr.api.get_leave_approver", "get"),
            ("cancel", "/method/hrms_tr.api.cancel_leave", "post"),
        )
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    contract_path = Path(__file__).resolve().with_name("hrms_tr.openapi.yaml")
    if not contract_path.is_file():
        contract_path = Path(__file__).resolve().parents[2] / "contracts/hrms_tr.openapi.yaml"
    parser.add_argument("--contract", type=Path, default=contract_path)
    parser.add_argument("--with-ai", action="store_true")
    parser.add_argument("tests", nargs="*")
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
    LeaveHttpTest.password = os.environ["HRT_TEST_PASSWORD"]
    LeaveHttpTest.with_ai = args.with_ai
    LeaveHttpTest.contract_validators = load_contract_validators(args.contract)
    unittest.main(argv=[__file__, *args.tests], verbosity=2)
