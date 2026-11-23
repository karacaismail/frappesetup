"""Bind the local Press review account to its Keycloak identity. Runs in the stack's Press bench.

Input on stdin: issuer and accounts (email, subject). Uses the same binding as the first Press
sign-in, so a repeated run keeps the existing link. Output on stdout: the users it prepared.
No password reaches Press: sign-in goes through Keycloak.
"""

import json
import os
import sys

import frappe

SITE = "press.localhost"


def main():
    payload = json.load(sys.stdin)
    os.chdir("sites")
    frappe.init(site=SITE, sites_path=".")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        from press_tr.press_identity.identity import bind_identity

        users = [
            bind_identity(
                {"iss": payload["issuer"], "sub": account["subject"], "email": account["email"],
                 "email_verified": True}
            ).user
            for account in payload["accounts"]
        ]
        frappe.db.commit()
    finally:
        frappe.destroy()
    print(json.dumps({"users": users}))


if __name__ == "__main__":
    main()
