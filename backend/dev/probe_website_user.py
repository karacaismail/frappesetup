"""Verify a Website User through Frappe's real HTTP login and API v2 paths."""

import argparse
import http.cookiejar
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def probe(site: str, port: int) -> None:
    import frappe

    bench = Path("/home/frappe/frappe-bench")
    os.chdir(bench / "sites")
    frappe.init(site=site)
    frappe.connect()
    if not site.startswith("test-") or not frappe.conf.allow_tests:
        frappe.destroy()
        raise SystemExit("This probe requires a separate test site with allow_tests.")

    suffix = secrets.token_hex(5)
    role = f"Dev Reader {suffix}"
    doctype = f"Dev Probe {suffix}"
    email = f"dev-reader-{suffix}@example.test"
    password = secrets.token_urlsafe(32)
    created = []
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )

    def request(path: str, data=None) -> tuple[int, dict]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url + path, data=body, headers={"Host": f"{site}:{port}"})
        try:
            response = opener.open(req, timeout=20)
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        with response:
            return response.status, json.load(response)

    try:
        frappe.set_user("Administrator")
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert()
        created.append(("Role", role))
        frappe.get_doc(
            {
                "doctype": "DocType",
                "name": doctype,
                "module": "Custom",
                "custom": 1,
                "autoname": "hash",
                "fields": [
                    {
                        "fieldname": "sample",
                        "fieldtype": "Data",
                        "label": "Sample",
                        "description": "Synthetic value used only by the local API permission probe.",
                    }
                ],
                "permissions": [{"role": role, "read": 1}],
            }
        ).insert()
        created.append(("DocType", doctype))
        doc = frappe.get_doc({"doctype": doctype, "sample": "synthetic"}).insert()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Synthetic",
                "user_type": "Website User",
                "send_welcome_email": 0,
                "new_password": password,
                "roles": [{"role": role}],
            }
        ).insert()
        created.append(("User", email))
        frappe.db.commit()
        if frappe.db.get_value("User", email, "user_type") != "Website User":
            raise AssertionError("Fixture is not a Website User")
        if frappe.db.get_value("Role", role, "desk_access"):
            raise AssertionError("Fixture role unexpectedly grants Desk access")

        status, _ = request("/api/method/login", {"usr": email, "pwd": password})
        if status != 200:
            raise AssertionError(f"Login returned {status}")
        path = "/api/v2/document/" + urllib.parse.quote(doctype) + "/" + urllib.parse.quote(doc.name)
        status, data = request(path)
        if status != 200 or data.get("data", {}).get("sample") != "synthetic":
            raise AssertionError(f"Allowed API v2 read returned {status}")
        status, _ = request("/api/v2/document/User/Administrator")
        if status != 403:
            raise AssertionError(f"Forbidden API v2 read returned {status}")
        print("PASS Website User login=200, own permitted DocType=200, forbidden User=403")
    finally:
        try:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            for kind, name in reversed(created):
                frappe.delete_doc(kind, name, force=True, ignore_missing=True)
            frappe.db.commit()
        finally:
            frappe.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="test-platform-core.localhost")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1000 <= args.port <= 65535:
        parser.error("Expected a port between 1000 and 65535")
    probe(args.site, args.port)


if __name__ == "__main__":
    main()
