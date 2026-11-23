"""Seed the Press side of the deletion chain test. Runs in the stack's Press bench.

Input on stdin: issuer, subject, email. Binds the synthetic identity to a Press user, as the first
Press sign-in would, and opens an Administrator session for the read checks.
Output on stdout: the E2E_* values the test reads.
"""

import json
import os
import sys
from hashlib import sha256

import frappe

SITE = "press.localhost"


def seed(issuer, subject, email):
    from press_tr.press_identity.identity import bind_identity

    link = bind_identity({"iss": issuer, "sub": subject, "email": email, "email_verified": True})
    return {
        "E2E_DELETE_PRESS_ANONYMOUS_USER": f"deleted-{sha256(link.name.encode()).hexdigest()[:32]}@invalid.example",
        "E2E_DELETE_PRESS_READER_COOKIE": "sid=" + administrator_session(),
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
