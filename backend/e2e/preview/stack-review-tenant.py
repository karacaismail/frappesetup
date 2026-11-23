"""Give the local review accounts their tenant roles. Runs in the stack's tenant-web container.

Input on stdin: issuer and accounts (email, subject, first_name, last_name, tenant_roles, employee).
Creates or updates each Frappe user, links it to its Keycloak identity as the first sign-in would,
adds the listed roles and, for an employee account, one synthetic Employee record.
Output on stdout: the users it prepared. No password reaches the tenant: sign-in goes through Keycloak.
"""

import json
import os
import sys

import frappe
from frappe.utils import add_days, today

SITE = "tenant1.localhost"
COMPANY = "Review Synthetic"
LINK = "PLT Identity Link"


def insert(doctype, **fields):
    return frappe.get_doc({"doctype": doctype, **fields}).insert()


def ensure_company():
    if frappe.db.exists("Company", COMPANY):
        return COMPANY
    if not frappe.db.exists("Warehouse Type", "Transit"):
        insert("Warehouse Type", name="Transit")
    return insert(
        "Company", company_name=COMPANY, abbr="REVS", default_currency="TRY", country="Türkiye"
    ).name


def ensure_user(issuer, account):
    from platform_core.identity import sign_in

    email = account["email"]
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.new_doc("User")
        user.update({"email": email, "send_welcome_email": 0})
        user.flags.no_welcome_mail = True
    user.update({"first_name": account["first_name"], "last_name": account["last_name"], "enabled": 1})
    user.save()
    linked = frappe.db.get_value(LINK, {"issuer": issuer, "subject": account["subject"]}, "user")
    if linked and linked != email:
        raise SystemExit(f"The Keycloak identity of {email} is linked to another user.")
    if not linked:
        sign_in.create_link(issuer, account["subject"], email)
    missing = [role for role in account["tenant_roles"] if role not in frappe.get_roles(email)]
    if missing:
        user.add_roles(*missing)
    if account.get("employee") and not frappe.db.exists("Employee", {"user_id": email}):
        if not frappe.db.exists("Gender", "Other"):
            insert("Gender", gender="Other")
        insert(
            "Employee",
            first_name=account["first_name"],
            last_name=account["last_name"],
            company=ensure_company(),
            status="Active",
            gender="Other",
            date_of_birth="1990-01-01",
            date_of_joining=add_days(today(), -30),
            user_id=email,
            create_user_permission=0,
        )
    return email


def main():
    payload = json.load(sys.stdin)
    os.chdir("sites")
    frappe.init(site=SITE, sites_path=".")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        users = [ensure_user(payload["issuer"], account) for account in payload["accounts"]]
        frappe.db.commit()
    finally:
        frappe.destroy()
    print(json.dumps({"users": users}))


if __name__ == "__main__":
    main()
