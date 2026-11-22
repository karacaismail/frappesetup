"""Create O-31 data only on a disposable HRMS test site."""

from contextlib import contextmanager
from dataclasses import dataclass
from time import time
from types import SimpleNamespace
from uuid import uuid4

import frappe
from frappe.utils import now_datetime
from platform_core.mobil.store import MobileStore

from . import fixture

EMPLOYEES = 200
LEAVE_PER_EMPLOYEE = 10
BACKLOG = 1_000
RECORD_TYPE = "fixture"


@dataclass(frozen=True)
class Phone:
    account: str
    token: str
    installation: str
    sid: str
    record: str
    version: str


@contextmanager
def test_database():
    frappe.init(fixture.SITE)
    try:
        fixture._require_test_site()
        frappe.connect()
        yield
    finally:
        frappe.destroy()


def _insert_rows(doctype, columns, rows, timestamp):
    # Synthetic benchmark rows must never run HR workflows, notifications or approvals.
    fields = ["creation", "modified", "owner", "modified_by", *columns]
    values = ((timestamp, timestamp, owner, "Administrator", *cells) for owner, *cells in rows)
    frappe.db.bulk_insert(doctype, fields, values)


def _leave_documents(phone, number, company, leave_type):
    for index in range(LEAVE_PER_EMPLOYEE):
        day = f"2025-06-{index + 1:02d}"
        yield (
            phone.account,
            f"O31-LV-{number:03d}-{index:02d}",
            f"O31-EMP-{number:03d}",
            f"O31 Employee {number}",
            company,
            leave_type,
            day,
            day,
            1,
            "Open",
        )


def _record_row(account, record_id, title):
    return account, record_id, record_id, title, fixture._scope_key(account, record_id)


def seed_site(samples):
    with test_database():
        installed = set(frappe.get_installed_apps())
        if not {"erpnext", "hrms", "platform_core", "mobile_test_app"} <= installed:
            raise SystemExit("Use a disposable test site with ERPNext, HRMS and mobile_test_app installed.")
        for doctype in ("Employee", "Leave Application", "Mobile Installation", fixture.RECORD):
            if frappe.db.count(doctype):
                raise SystemExit(f"The benchmark requires an empty {doctype} table.")
        timestamp = now_datetime()
        phones = []
        leave = []
        projections = []
        company = "O31 Test Company"
        leave_type = "O31 Test Leave"
        _insert_rows(
            "Company",
            ["name", "company_name", "abbr", "default_currency"],
            [("Administrator", company, company, "O31", "USD")],
            timestamp,
        )
        _insert_rows(
            "Leave Type",
            ["name", "leave_type_name"],
            [("Administrator", leave_type, leave_type)],
            timestamp,
        )

        employees = []
        frappe.flags.in_import = True
        for number in range(1, EMPLOYEES + 1):
            account = f"o31-employee-{number:03d}@example.test"
            frappe.get_doc(
                doctype="User", email=account, first_name=f"O31 {number}", enabled=1, send_welcome_email=0
            ).insert()
            phone = Phone(
                account, f"fixture-o31-{number:03d}", str(uuid4()), str(uuid4()), str(uuid4()), str(timestamp)
            )
            phones.append(phone)
            employees.append(
                (
                    account,
                    f"O31-EMP-{number:03d}",
                    f"O31 {number}",
                    f"O31 Employee {number}",
                    company,
                    account,
                    "Active",
                )
            )
            leave.extend(_leave_documents(phone, number, company, leave_type))
            for index in range(LEAVE_PER_EMPLOYEE):
                record_id = phone.record if index == 0 else str(uuid4())
                projections.append(_record_row(account, record_id, f"Test leave {index + 1}"))
        _insert_rows(
            "Employee",
            ["name", "first_name", "employee_name", "company", "user_id", "status"],
            employees,
            timestamp,
        )
        _insert_rows(
            "Leave Application",
            [
                "name",
                "employee",
                "employee_name",
                "company",
                "leave_type",
                "from_date",
                "to_date",
                "total_leave_days",
                "status",
            ],
            leave,
            timestamp,
        )
        _insert_rows(fixture.RECORD, ["name", "record_id", "title", "scope_key"], projections, timestamp)

        store = MobileStore()
        started = int(time())
        for phone in phones[samples:]:
            identity = SimpleNamespace(
                account=phone.account,
                scope="mobile",
                principal=fixture.content_digest(["fixture", fixture._subject(phone.account)]),
                sid=phone.sid,
                subject=fixture._subject(phone.account),
                auth_time=started,
            )
            store.install(identity, phone.installation)
        # The offline seed must be visible to the HTTP worker.
        frappe.db.commit()  # nosemgrep: frappe-request-commit
        return phones


def seed_backlog(phone):
    with test_database():
        records = [str(uuid4()) for _ in range(BACKLOG)]
        timestamp = now_datetime()
        _insert_rows(
            fixture.RECORD,
            ["name", "record_id", "title", "scope_key"],
            (_record_row(phone.account, record_id, "Pending test leave change") for record_id in records),
            timestamp,
        )
        store = MobileStore()
        for record_id in records:
            store.append_change(RECORD_TYPE, record_id, "upsert", target_installation=phone.installation)
        # The offline seed must be visible to the HTTP worker.
        frappe.db.commit()  # nosemgrep: frappe-request-commit


def verify_counts():
    with test_database():
        counts = tuple(
            frappe.db.count(table) for table in ("Employee", "Leave Application", "Mobile Installation")
        )
        expected = (EMPLOYEES, EMPLOYEES * LEAVE_PER_EMPLOYEE, EMPLOYEES)
        accounts = frappe.get_all("Mobile Installation", limit=EMPLOYEES, pluck="account")
        if counts != expected or len(set(accounts)) != EMPLOYEES:
            raise RuntimeError(f"Unexpected benchmark data counts: {counts}. Expected: {expected}.")
