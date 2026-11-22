"""Create O-31 data only on a disposable HRMS test site."""

import re
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import time
from types import SimpleNamespace
from uuid import uuid4

import frappe
from frappe.utils import now_datetime
from frappe.utils.background_jobs import get_queues
from platform_core.mobil.protocol import operation_key
from platform_core.mobil.store import MobileStore

from . import fixture

EMPLOYEES = 200
LEAVE_PER_EMPLOYEE = 10
BACKLOG = 1_000
RECORD_TYPE = "fixture"


@dataclass(frozen=True)
class Phone:
    site: str
    account: str
    token: str
    installation: str
    sid: str
    record: str
    version: str
    operation_id: str


def require_performance_site(site, sites_path="."):
    if not re.fullmatch(r"perf-[a-z0-9-]+\.localhost", site):
        raise SystemExit("Use a perf-*.localhost site for the benchmark.")
    config_path = Path(sites_path) / site / "site_config.json"
    config = frappe.get_file_json(config_path)
    enabled = config.get("allow_performance_fixture")
    if type(enabled) is not int or enabled != 1:
        raise SystemExit("Set allow_performance_fixture to 1 in the site's configuration.")


@contextmanager
def test_database(site):
    require_performance_site(site)
    frappe.init(site)
    try:
        frappe.connect()
        yield
    finally:
        frappe.destroy()


def require_empty_queue():
    # Read queue state. Do not run workers, remove jobs or clean Redis registries.
    for queue in get_queues():
        if queue.count or any(
            queue.connection.zcard(registry.key)
            for registry in (
                queue.started_job_registry,
                queue.deferred_job_registry,
                queue.scheduled_job_registry,
            )
        ):
            raise SystemExit("The bench queue must be empty before the benchmark.")


def _insert_rows(doctype, columns, rows, timestamp, created):
    # Raw fixture rows avoid business workflows and background jobs, including User contact creation.
    fields = ["creation", "modified", "owner", "modified_by", *columns]
    values = [(timestamp, timestamp, owner, "Administrator", *cells) for owner, *cells in rows]
    frappe.db.bulk_insert(doctype, fields, values)
    created.extend((doctype, row[4]) for row in values)


def delete_records(records):
    by_type = defaultdict(list)
    for doctype, name in records:
        by_type[doctype].append(name)
    for doctype, names in by_type.items():
        frappe.db.delete(doctype, {"name": ["in", names]})


@contextmanager
def performance_fixture(site, samples):
    created = []
    phones = seed_site(site, samples, created)
    try:
        yield phones, created
    finally:
        with test_database(site):
            installations = [phone.installation for phone in phones]
            record_ids = [name for doctype, name in created if doctype == fixture.RECORD]
            for doctype, field, values in (
                ("Mobile Delivery", "installation_id", installations),
                ("Mobile Change", "record_id", record_ids),
            ):
                for name in frappe.get_all(doctype, filters={field: ["in", values]}, pluck="name"):
                    created.append((doctype, name))
            for phone in phones:
                principal = fixture.content_digest(["fixture", fixture._subject(phone.account)])
                created.extend(
                    (
                        ("Mobile Operation", operation_key(site, principal, phone.operation_id)),
                        ("Mobile Installation", phone.installation),
                        ("Mobile Account State", phone.account),
                    )
                )
            delete_records(reversed(created))
            frappe.db.commit()  # nosemgrep: frappe-request-commit


def _leave_documents(phone, employee, number, company, leave_type):
    for index in range(LEAVE_PER_EMPLOYEE):
        day = f"2025-06-{index + 1:02d}"
        yield (
            phone.account,
            f"{employee}-LV-{index:02d}",
            employee,
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


def seed_site(site, samples, created):
    with test_database(site):
        require_empty_queue()
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
        run = uuid4().hex
        company = f"O31 Company {run}"
        leave_type = f"O31 Leave {run}"
        _insert_rows(
            "Company",
            ["name", "company_name", "abbr", "default_currency"],
            [("Administrator", company, company, run[:5], "USD")],
            timestamp,
            created,
        )
        _insert_rows(
            "Leave Type",
            ["name", "leave_type_name"],
            [("Administrator", leave_type, leave_type)],
            timestamp,
            created,
        )

        employees = []
        users = []
        for number in range(1, EMPLOYEES + 1):
            account = f"o31-{run}-{number:03d}@example.test"
            employee = f"O31-{run}-{number:03d}"
            full_name = f"O31 Employee {number}"
            users.append(("Administrator", account, account, full_name, full_name, "Website User", 1))
            phone = Phone(
                site,
                account,
                f"fixture-{uuid4().hex}",
                str(uuid4()),
                str(uuid4()),
                str(uuid4()),
                str(timestamp),
                str(uuid4()),
            )
            phones.append(phone)
            employees.append(
                (
                    account,
                    employee,
                    f"O31 {number}",
                    f"O31 Employee {number}",
                    company,
                    account,
                    "Active",
                )
            )
            leave.extend(_leave_documents(phone, employee, number, company, leave_type))
            for index in range(LEAVE_PER_EMPLOYEE):
                record_id = phone.record if index == 0 else str(uuid4())
                projections.append(_record_row(account, record_id, f"Test leave {index + 1}"))
        _insert_rows(
            "User",
            ["name", "email", "first_name", "full_name", "user_type", "enabled"],
            users,
            timestamp,
            created,
        )
        _insert_rows(
            "Employee",
            ["name", "first_name", "employee_name", "company", "user_id", "status"],
            employees,
            timestamp,
            created,
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
            created,
        )
        _insert_rows(
            fixture.RECORD, ["name", "record_id", "title", "scope_key"], projections, timestamp, created
        )

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


def seed_backlog(phone, created):
    with test_database(phone.site):
        records = [str(uuid4()) for _unused in range(BACKLOG)]
        timestamp = now_datetime()
        _insert_rows(
            fixture.RECORD,
            ["name", "record_id", "title", "scope_key"],
            (_record_row(phone.account, record_id, "Pending test leave change") for record_id in records),
            timestamp,
            created,
        )
        store = MobileStore()
        for record_id in records:
            store.append_change(RECORD_TYPE, record_id, "upsert", target_installation=phone.installation)
        # The offline seed must be visible to the HTTP worker.
        frappe.db.commit()  # nosemgrep: frappe-request-commit


def verify_counts(site):
    with test_database(site):
        counts = tuple(
            frappe.db.count(table) for table in ("Employee", "Leave Application", "Mobile Installation")
        )
        expected = (EMPLOYEES, EMPLOYEES * LEAVE_PER_EMPLOYEE, EMPLOYEES)
        accounts = frappe.get_all("Mobile Installation", limit=EMPLOYEES, pluck="account")
        if counts != expected or len(set(accounts)) != EMPLOYEES:
            raise RuntimeError(f"Unexpected benchmark data counts: {counts}. Expected: {expected}.")
