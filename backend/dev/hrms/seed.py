"""Seed one isolated HRMS TR test site with synthetic employees and requests."""

import argparse
import json
import os
import re
from pathlib import Path

import frappe
from frappe.utils import add_days, today

COMPANY = "HRMS TR Synthetic"
LEAVE_TYPE = "HRMS TR Synthetic Unpaid"
ALLOCATED_LEAVE_TYPE = "HRMS TR Synthetic Annual"
USERS = {actor: f"hrms-tr-{actor}@example.test" for actor in ("employee", "manager", "outsider", "hr")}
OPERATIONS_ROLES = ("System Manager", "HR Manager")
LEGACY_ROLES = ("HR User", "Leave Approver", "Employee")
ROLES = {
    "employee": "Employee",
    "manager": "Manager",
    "outsider": "Employee",
    "hr": "Admin",
}


def insert(doctype, **fields):
    return frappe.get_doc({"doctype": doctype, **fields}).insert()


def seed(password, *, performance=False):
    if frappe.db.exists("Company", COMPANY):
        raise SystemExit("Start with a fresh test site before seeding.")
    if not performance:
        frappe.db.set_single_value("System Settings", "enable_telemetry", 0)
    if not frappe.db.exists("Warehouse Type", "Transit"):
        insert("Warehouse Type", name="Transit")
    holiday_list = insert(
        "Holiday List",
        holiday_list_name=COMPANY,
        from_date=add_days(today(), -30),
        to_date=add_days(today(), 90),
    )
    company = insert(
        "Company",
        company_name=COMPANY,
        abbr="CHRT",
        default_currency="TRY",
        country="Türkiye",
    )
    insert(
        "Holiday List Assignment",
        naming_series="HR-HLA-.YYYY.-",
        applicable_for="Company",
        assigned_to=company.name,
        holiday_list=holiday_list.name,
        from_date=holiday_list.from_date,
    ).submit()
    leave_type = insert("Leave Type", leave_type_name=LEAVE_TYPE, is_lwp=1, include_holiday=1)
    if not frappe.db.exists("Gender", "Other"):
        insert("Gender", gender="Other")
    if performance:
        insert(
            "User",
            email=USERS["hr"],
            first_name="HRMS TR Performance Reviewer",
            send_welcome_email=0,
            new_password=password,
            user_type="Website User",
            role_profiles=[{"role_profile": "HRT Admin"}],
        )
        return
    allocated_type = insert("Leave Type", leave_type_name=ALLOCATED_LEAVE_TYPE, include_holiday=1)
    frappe.db.set_single_value(
        "HR Settings",
        {
            "send_leave_notification": 0,
            "leave_approver_mandatory_in_leave_application": 0,
        },
    )

    employees = {}
    for actor in ("manager", "employee", "outsider", "hr"):
        username = USERS[actor]
        insert(
            "User",
            email=username,
            first_name=f"HRMS TR {actor}",
            send_welcome_email=0,
            new_password=password,
            user_type="Website User",
            role_profiles=[{"role_profile": f"HRT {ROLES[actor]}"}],
        )
        employees[actor] = insert(
            "Employee",
            first_name=f"HRMS TR {actor}",
            company=company.name,
            status="Active",
            gender="Other",
            date_of_birth="1990-01-01",
            date_of_joining=add_days(today(), -30),
            user_id=username,
            create_user_permission=0,
            reports_to=employees.get("manager") if actor == "employee" else None,
            leave_approver=USERS["manager"] if actor == "employee" else None,
        ).name

    legacy_users = {}
    for index, role in enumerate((*OPERATIONS_ROLES, *LEGACY_ROLES)):
        username = f"hrms-tr-legacy-{index}@example.test"
        legacy_user = insert(
            "User",
            email=username,
            first_name=f"Synthetic Legacy User {index}",
            send_welcome_email=0,
            new_password=password,
            roles=[] if role == "Employee" else [{"role": role}],
        )
        if role == "Employee":
            insert(
                "Employee",
                first_name="Synthetic Legacy Employee",
                company=company.name,
                status="Active",
                gender="Other",
                date_of_birth="1990-01-01",
                date_of_joining=add_days(today(), -30),
                user_id=username,
                create_user_permission=0,
            )
            legacy_user.reload()
            legacy_user.add_roles(role)
        legacy_users[role] = username

    for actor in ("employee", "outsider"):
        insert(
            "Leave Allocation",
            employee=employees[actor],
            company=company.name,
            leave_type=allocated_type.name,
            from_date=add_days(today(), -1),
            to_date=add_days(today(), 30),
            new_leaves_allocated=12,
        ).submit()

    leaves = {}
    leave_owners = {}
    for offset, (key, actor) in enumerate(
        (
            ("employee", "employee"),
            ("manager", "manager"),
            ("outsider", "outsider"),
            ("ai", "employee"),
            ("ai_stale", "employee"),
            ("hr", "hr"),
            ("hr_approve", "outsider"),
            ("manager_approve", "employee"),
            ("system_manager_approve", "outsider"),
            ("hr_manager_approve", "outsider"),
            ("manager_edit", "employee"),
            ("website_approval", "employee"),
        ),
        start=2,
    ):
        date = add_days(today(), offset)
        leave = insert(
            "Leave Application",
            employee=employees[actor],
            company=company.name,
            leave_type=leave_type.name,
            from_date=date,
            to_date=date,
            posting_date=today(),
            status="Open",
        )
        leave.db_set("leave_balance", 7, update_modified=False)
        leaves[key] = leave.name
        leave_owners[key] = actor

    prepared = frappe.get_doc(
        {
            "doctype": "Prepared Report",
            "report_name": "Leave Ledger",
            "status": "Completed",
        }
    )
    prepared.db_insert()
    attachment = insert(
        "File",
        file_name="hrms-tr-synthetic-leave-report.txt",
        is_private=1,
        content="Synthetic result from an old leave report.",
    )

    # Recreate an attachment saved before the report was disabled.
    attachment.db_set({"attached_to_doctype": "Prepared Report", "attached_to_name": prepared.name})

    return {
        "prepared_report": prepared.name,
        "prepared_report_file": attachment.file_url,
        "users": USERS,
        "legacy_users": legacy_users,
        "employees": employees,
        "leaves": leaves,
        "leave_owners": leave_owners,
        "allocated_leave_type": allocated_type.name,
    }


def seed_permission_matrix(password, data):
    roleless = insert(
        "User",
        email="hrms-tr-roleless@example.test",
        first_name="Synthetic Roleless User",
        user_type="Website User",
        new_password=password,
        send_welcome_email=0,
    )
    roleless_employee = insert(
        "Employee",
        first_name="Synthetic Roleless Employee",
        company=COMPANY,
        gender="Other",
        status="Active",
        date_of_birth="1990-01-01",
        date_of_joining=add_days(today(), -30),
        user_id=roleless.name,
        create_user_permission=0,
    )
    foreign = insert(
        "User",
        email="hrms-tr-foreign-hr@example.test",
        first_name="Synthetic Foreign HR",
        user_type="Website User",
        new_password=password,
        send_welcome_email=0,
        role_profiles=[{"role_profile": "HRT Admin"}],
    )
    company = insert(
        "Company",
        company_name="HRMS TR Foreign Synthetic",
        abbr="FHR",
        default_currency="TRY",
        country="Türkiye",
    )
    day = add_days(today(), 32)
    employee = insert(
        "Employee",
        first_name="Synthetic Foreign Employee",
        company=company.name,
        gender="Other",
        status="Active",
        date_of_birth="1990-01-01",
        date_of_joining=add_days(today(), -30),
        create_user_permission=0,
    )
    leave = insert(
        "Leave Application",
        employee=employee.name,
        company=company.name,
        leave_type=LEAVE_TYPE,
        from_date=day,
        to_date=day,
        posting_date=today(),
        status="Open",
    )
    insert(
        "User Permission",
        user=foreign.name,
        allow="Company",
        for_value=company.name,
        apply_to_all_doctypes=1,
    )
    attendance = insert(
        "Attendance Request",
        employee=data["employees"]["employee"],
        from_date=add_days(today(), 61),
        to_date=add_days(today(), 61),
        reason="Work From Home",
    )
    draft = insert(
        "Leave Application",
        employee=data["employees"]["employee"],
        company=COMPANY,
        leave_type=LEAVE_TYPE,
        from_date=day,
        to_date=day,
        posting_date=today(),
        status="Open",
    )
    data["employees"]["foreign"] = employee.name
    data["leaves"].update(d6=draft.name, foreign=leave.name)
    data["leave_owners"].update(d6="employee", foreign="foreign")
    data["d6"] = {
        "roleless": roleless.name,
        "roleless_employee": roleless_employee.name,
        "foreign": foreign.name,
        "attendance": attendance.name,
    }


def seed_concurrency(password, data):
    reviewer = insert(
        "User",
        email="hrms-tr-race-reviewer@example.test",
        first_name="Synthetic Second Reviewer",
        user_type="Website User",
        role_profiles=[{"role_profile": "HRT Admin"}],
        new_password=password,
        send_welcome_email=0,
    )
    day = add_days(today(), 36)
    application = insert(
        "Leave Application",
        employee=data["employees"]["employee"],
        company=COMPANY,
        leave_type=LEAVE_TYPE,
        from_date=day,
        to_date=day,
        posting_date=today(),
        status="Open",
    )
    data["leaves"]["concurrent"] = application.name
    data["leave_owners"]["concurrent"] = "employee"
    actors = []
    for number in range(1, 21):
        actor = f"concurrent-{number}"
        user = insert(
            "User",
            email=f"hrms-tr-{actor}@example.test",
            first_name=f"Synthetic Requester {number}",
            user_type="Website User",
            role_profiles=[{"role_profile": "HRT Employee"}],
            new_password=password,
            send_welcome_email=0,
        )
        employee = insert(
            "Employee",
            first_name=user.first_name,
            company=COMPANY,
            gender="Other",
            status="Active",
            date_of_birth="1990-01-01",
            date_of_joining=add_days(today(), -30),
            user_id=user.name,
            create_user_permission=0,
        )
        data["users"][actor] = user.name
        data["employees"][actor] = employee.name
        actors.append(actor)
    data["concurrency"] = {
        "reviewer": reviewer.name,
        "employees": actors,
        "request_day": day,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"test-[a-z0-9-]+\.localhost", args.site):
        parser.error("Use a dedicated test-*.localhost site.")
    password = os.environ["HRT_TEST_PASSWORD"]
    manifest = args.manifest.resolve()
    os.chdir("sites")
    frappe.init(site=args.site, sites_path=".")
    try:
        frappe.connect()
        if not frappe.conf.allow_tests:
            raise SystemExit("The site must have allow_tests enabled.")
        frappe.set_user("Administrator")
        data = seed(password)
        seed_permission_matrix(password, data)
        seed_concurrency(password, data)
        frappe.db.commit()
        manifest.write_text(json.dumps(data, indent=2) + "\n")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
