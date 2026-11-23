"""Seed the tenant side of the Press deletion chain test (MVP test 2, row 5e).

Runs in the stack's tenant-web container. Input on stdin: issuer, subject, email.
Creates the identity link through the real provisioning path, one synthetic company and one
Employee with personal fields, and an Administrator session for the read checks.
Output on stdout: the E2E_* values the test reads.
"""

import json
import os
import sys

import frappe
from frappe.utils import add_days, today

SITE = "tenant1.localhost"
COMPANY = "E2E Deletion Synthetic"


def insert(doctype, **fields):
    return frappe.get_doc({"doctype": doctype, **fields}).insert()


def ensure_company():
    if frappe.db.exists("Company", COMPANY):
        return COMPANY
    if not frappe.db.exists("Warehouse Type", "Transit"):
        insert("Warehouse Type", name="Transit")
    return insert(
        "Company", company_name=COMPANY, abbr="E2ED", default_currency="TRY", country="Türkiye"
    ).name


def seed(issuer, subject, email):
    from platform_core.identity.anonymization import identity_hash
    from platform_core.identity.provisioning import provision

    provision(
        {
            "issuer": issuer,
            "subject": subject,
            "email": email,
            "email_verified": True,
            "enabled": True,
            "first_name": "Synthetic",
            "last_name": "Deletion",
        }
    )
    company = ensure_company()
    if not frappe.db.exists("Gender", "Other"):
        insert("Gender", gender="Other")
    suffix = email.split("@", 1)[0].rsplit("-", 1)[-1]
    employee = insert(
        "Employee",
        first_name="Synthetic",
        middle_name="Example",
        last_name="Deletion",
        company=company,
        status="Active",
        gender="Other",
        date_of_birth="1990-01-01",
        date_of_joining=add_days(today(), -30),
        user_id=email,
        create_user_permission=0,
        personal_email=f"personal-{suffix}@example.test",
        company_email=f"company-{suffix}@example.test",
        prefered_contact_email="Personal Email",
        cell_number="+90 200 000 00 00",
        emergency_phone_number="+90 200 000 00 01",
        person_to_be_contacted="Synthetic Emergency Contact",
        relation="Synthetic relation",
        # Frappe checks the IBAN checksum. This is the public example number, not an account.
        iban="TR330006100519786457841326",
        bank_name="Synthetic Bank",
        bank_ac_no="NOT-A-BANK-ACCOUNT",
        blood_group="A+",
        marital_status="Single",
        current_address="Synthetic current address",
        permanent_address="Synthetic permanent address",
        bio="Synthetic biography",
        attendance_device_id=f"SYNTHETIC-DEVICE-{suffix}",
    )
    anonymous = f"deleted-user-{identity_hash(issuer, subject)[:16]}@deleted.invalid"
    return {
        "E2E_DELETE_EMPLOYEE": employee.name,
        "E2E_DELETE_TENANT_ANONYMOUS_USER": anonymous,
        "E2E_DELETE_TENANT_READER_COOKIE": "sid=" + administrator_session(),
    }


def administrator_session():
    from frappe.sessions import Session
    from werkzeug.wrappers import Request

    frappe.local.request = Request.from_values()
    frappe.local.request_ip = "127.0.0.1"
    return Session("Administrator", full_name="Administrator", user_type="System User").sid


def main():
    payload = json.load(sys.stdin)
    os.chdir("sites")
    frappe.init(site=SITE, sites_path=".")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        fixture = seed(payload["issuer"], payload["subject"], payload["email"])
        frappe.db.commit()
    finally:
        frappe.destroy()
    print(json.dumps(fixture))


if __name__ == "__main__":
    main()
