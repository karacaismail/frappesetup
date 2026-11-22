"""Configure only the Press development site owned by e2e/stack."""

import json
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import frappe


def ensure_sync_user(email):
    account = frappe.db.get_value("User", email, ["enabled", "user_type"])
    if account is None:
        frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "Identity Sync",
            "user_type": "Website User",
            "send_welcome_email": 0,
        }).insert()
    elif not account[0] or account[1] != "Website User":
        raise ValueError("The Press identity sync account must be an enabled Website User.")


def main():
    settings = json.load(sys.stdin)
    os.chdir("sites")
    site = "press.localhost"
    path = Path(site) / "site_config.json"
    config = json.loads(path.read_text())

    frappe.init(site=site, sites_path=".")
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        ensure_sync_user(settings["press_identity_sync_user"])
        frappe.db.commit()
    finally:
        frappe.destroy()

    config.update(settings)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(json.dumps(config, indent=2) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
