"""Measure the O-31 HRMS TR workload on an empty, dedicated test site."""

import argparse
import os
import re
import sys
from contextlib import redirect_stdout
from math import ceil
from time import perf_counter
from urllib.parse import quote

import frappe
from frappe.app import application
from frappe.utils import add_days, today
from frappe.utils.background_jobs import get_queues, get_running_jobs_in_queue
from seed import COMPANY, LEAVE_TYPE, USERS, insert, seed
from werkzeug.test import Client

EMPLOYEES = 200
LEAVES = 2_000
SAMPLES = 50
READ_LIMIT_MS = 500
WRITE_LIMIT_MS = 1_000
RESOURCE = "/api/resource/Leave%20Application"
METHOD = "/api/method/hrms_tr.api."
DENIAL = "/api/method/hrms_tr.hrms_endpoints.deny_legacy_leave_query"
PERFORMANCE_SITE = re.compile(r"perf-[a-z0-9-]+\.localhost")


def make_workload(site, password):
    if not PERFORMANCE_SITE.fullmatch(site):
        raise SystemExit("Use a dedicated perf-*.localhost site.")
    frappe.init(site=site, sites_path=".")
    try:
        site_config = frappe.get_file_json(os.path.join(site, "site_config.json"))
        opt_in = site_config.get("allow_performance_fixture")
        if type(opt_in) is not int or opt_in != 1:
            raise SystemExit("The site must have allow_performance_fixture set to 1.")
        frappe.connect()
        if any(queue.count or get_running_jobs_in_queue(queue) for queue in get_queues()):
            raise SystemExit("The background job queue must be empty before seeding.")
        if frappe.db.count("Employee") or frappe.db.count("Leave Application"):
            raise SystemExit("Start with an empty HRMS TR test site.")
        frappe.set_user("Administrator")
        seed(password, performance=True)
        day = today()
        for ordinal in range(EMPLOYEES - frappe.db.count("Employee")):
            insert(
                "Employee",
                first_name=f"Measurement Employee {ordinal + 1}",
                company=COMPANY,
                status="Active",
                gender="Other",
                date_of_birth="1990-01-01",
                date_of_joining=add_days(day, -30),
                create_user_permission=0,
            )
        employees = frappe.get_all(
            "Employee",
            filters={"user_id": ["is", "not set"]},
            pluck="name",
            order_by="name asc",
        )
        draft_names = []
        records = []
        for ordinal in range(LEAVES - frappe.db.count("Leave Application")):
            offset, employee = divmod(ordinal, len(employees))
            leave_day = add_days(day, 35 + offset)
            leave = insert(
                "Leave Application",
                employee=employees[employee],
                company=COMPANY,
                leave_type=LEAVE_TYPE,
                from_date=leave_day,
                to_date=leave_day,
                posting_date=day,
                status="Open",
            )
            records.append((leave.doctype, leave.name))
            if ordinal < SAMPLES:
                draft_names.append(leave.name)
        attendance_day = add_days(day, 60)
        attendance = insert(
            "Attendance Request",
            employee=employees[0],
            from_date=attendance_day,
            to_date=attendance_day,
            reason="Work From Home",
        )
        records.append((attendance.doctype, attendance.name))
        if (
            frappe.db.count("Employee") != EMPLOYEES
            or frappe.db.count("Leave Application") != LEAVES
            or len(draft_names) != SAMPLES
        ):
            raise SystemExit("The workload does not match the O-31 record counts.")
        frappe.db.commit()
        return draft_names, employees, attendance.name, records
    finally:
        frappe.destroy()


def cleanup_records(records):
    for doctype, name in reversed(records):
        if frappe.db.exists(doctype, name) and frappe.get_doc(doctype, name).docstatus != 1:
            frappe.delete_doc(doctype, name, delete_permanently=True)


def cleanup_workload(site, records):
    frappe.init(site=site, sites_path=".")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        cleanup_records(records)
        frappe.db.commit()
    finally:
        frappe.destroy()


class MeasurementSession:
    def __init__(self, site, username, password, *, portal=False):
        self.client = Client(self.timed_wsgi)
        self.headers = {"X-Frappe-Site-Name": site, "Accept": "application/json"}
        self.call("POST", "/api/method/login", body={"usr": username, "pwd": password})
        if portal:
            page, _elapsed = self.call("GET", "/panel")
            token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data)
            if token is None or token[1] in (b"None", b"null"):
                raise SystemExit("The HR portal did not provide a CSRF token.")
            self.headers["X-Frappe-CSRF-Token"] = token[1].decode()

    def timed_wsgi(self, environ, start_response):
        started = perf_counter()
        body = application(environ, start_response)
        try:
            yield from body
        finally:
            if hasattr(body, "close"):
                body.close()
            self.elapsed = (perf_counter() - started) * 1_000

    def call(self, method, path, *, expected=200, query=None, body=None):
        response = self.client.open(
            path,
            method=method,
            headers=self.headers,
            query_string=query,
            json=body,
            buffered=True,
        )
        if response.status_code != expected:
            raise SystemExit(
                f"{method} {path.split('?')[0]} returned HTTP {response.status_code}. Expected {expected}."
            )
        return response, self.elapsed


def record_version(session, name):
    response, _elapsed = session.call("GET", f"{RESOURCE}/{quote(name, safe='')}")
    return {"name": name, "version": response.json["data"]["modified"]}


def measure(site, draft_names, employees, attendance, password):
    hr = MeasurementSession(site, USERS["hr"], password, portal=True)
    admin = MeasurementSession(site, "Administrator", os.environ["ADMIN_PASSWORD"])
    operations = {
        ("GET", RESOURCE, READ_LIMIT_MS): [],
        ("GET", f"{RESOURCE}/{{name}}", READ_LIMIT_MS): [],
        ("GET", f"{METHOD}get_leave_approver", READ_LIMIT_MS): [],
        ("POST", f"{METHOD}approve_leave", WRITE_LIMIT_MS): [],
        ("POST", f"{METHOD}cancel_leave", WRITE_LIMIT_MS): [],
    }
    for ordinal, name in enumerate(draft_names):
        read_name = f"{RESOURCE}/{quote(name, safe='')}"
        response, elapsed = hr.call(
            "GET",
            RESOURCE,
            query={
                "fields": '["name","status","modified"]',
                "order_by": "modified desc, name asc",
                "limit_page_length": 100,
                "limit_start": (ordinal * 100) % LEAVES,
            },
        )
        if len(response.json["data"]) != 100:
            raise SystemExit("The HR session did not see the expected page of leave records.")
        operations["GET", RESOURCE, READ_LIMIT_MS].append(elapsed)
        response, elapsed = hr.call("GET", read_name)
        operations["GET", f"{RESOURCE}/{{name}}", READ_LIMIT_MS].append(elapsed)
        version = {"name": name, "version": response.json["data"]["modified"]}
        _response, elapsed = hr.call("GET", f"{METHOD}get_leave_approver", query={"employee": employees[ordinal]})
        operations["GET", f"{METHOD}get_leave_approver", READ_LIMIT_MS].append(elapsed)
        _response, elapsed = hr.call("POST", f"{METHOD}approve_leave", body=version)
        operations["POST", f"{METHOD}approve_leave", WRITE_LIMIT_MS].append(elapsed)
        _response, elapsed = hr.call("POST", f"{METHOD}cancel_leave", body=record_version(hr, name))
        operations["POST", f"{METHOD}cancel_leave", WRITE_LIMIT_MS].append(elapsed)
    attendance_path = "/api/v2/document/Attendance%20Request/{name}/method/get_attendance_warnings/"
    for method in ("GET", "POST"):
        for route, path in (
            (DENIAL, DENIAL),
            (attendance_path, attendance_path.format(name=quote(attendance, safe=""))),
        ):
            operations[method, route, READ_LIMIT_MS] = [
                admin.call(method, path, expected=403)[1] for _iteration in range(SAMPLES)
            ]
    return operations


def report(revision, operations):
    print("\n## HRMS TR O-31 ölçümü\n")
    print(f"Git kaydı `{revision}`.")
    print(f"Test verisi {EMPLOYEES} çalışan ve {LEAVES} izin kaydı içerir.")
    print("Ölçüm, Frappe sunucusunun isteği işlemesi ve yanıtı üretmesi için geçen süreyi kapsar.")
    print("İstekler sırayla gönderildi. Ağ, oturum açma ve hazırlık ölçüme girmedi.")
    print("Engelli yollar 403 döndürdü. Bu yollar için okuma sınırı kullanıldı.\n")
    print("| Yöntem ve yol | Çağrı | p95 (ms) | Sınır (ms) | Sonuç |")
    print("| --- | ---: | ---: | ---: | --- |")
    failed = False
    for (method, path, limit), samples in operations.items():
        p95 = sorted(samples)[ceil(len(samples) * 0.95) - 1]
        passed = p95 <= limit
        failed |= not passed
        print(
            f"| `{method} {path}` | {len(samples)} | {p95:.2f} | {limit} | {'pass' if passed else 'fail'} |"
        )
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if not PERFORMANCE_SITE.fullmatch(args.site):
        parser.error("Use a dedicated perf-*.localhost site.")
    if not re.fullmatch(r"[0-9a-f]{7,40}", args.revision):
        parser.error("Pass the Git revision of the test image.")
    password = os.environ["HRT_TEST_PASSWORD"]
    os.chdir("sites")
    # Frappe prints tracebacks for the expected 403 responses. Only the report goes to stdout.
    with redirect_stdout(sys.stderr):
        drafts, employees, attendance, records = make_workload(args.site, password)
        try:
            operations = measure(args.site, drafts, employees, attendance, password)
        finally:
            cleanup_workload(args.site, records)
    return report(args.revision, operations)


if __name__ == "__main__":
    raise SystemExit(main())
