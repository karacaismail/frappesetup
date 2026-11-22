import frappe
import requests
from frappe.rate_limiter import rate_limit

# ruleid: frappe-missing-permission
@frappe.whitelist(methods=["GET"])
def unchecked():
    return frappe.get_doc("Note", "fixture").title

# ok: frappe-missing-permission
@frappe.whitelist(methods=["GET"])
def checked():
    note = frappe.get_doc("Note", "fixture")
    note.check_permission("read")
    return note.title

# ruleid: frappe-guest-without-limit
@frappe.whitelist(allow_guest=True, methods=["GET"])
def public_unlimited():
    frappe.get_doc("Note", "fixture").check_permission("read")
    return "fixture"

# ok: frappe-guest-without-limit
@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=5, seconds=60)
def public_limited():
    frappe.get_doc("Note", "fixture").check_permission("read")
    return "fixture"

# ruleid: frappe-missing-methods
@frappe.whitelist()
def unbounded_method():
    frappe.get_doc("Note", "fixture").check_permission("read")
    return "fixture"

# ok: frappe-missing-methods
@frappe.whitelist(methods=["GET"])
def get_only():
    frappe.get_doc("Note", "fixture").check_permission("read")
    return "fixture"

@frappe.whitelist(methods=["POST"])
def save(note):
    note.check_permission("write")
    # ruleid: frappe-request-commit
    frappe.db.commit()

def maintenance():
    # ok: frappe-request-commit
    frappe.db.commit()

def permission_flag(note):
    # ruleid: frappe-ignore-permissions
    note.save(ignore_permissions=True)
    # ok: frappe-ignore-permissions
    note.save(ignore_permissions=False)

def queries(field):
    # ruleid: frappe-built-sql
    frappe.db.sql(f"SELECT {field}")
    # ruleid: frappe-built-sql
    frappe.db.sql("SELECT {}".format(field))
    # ruleid: frappe-built-sql
    frappe.db.sql("SELECT " + field)
    # ok: frappe-built-sql
    frappe.db.sql("SELECT %s", (field,))

def execution(value):
    # ruleid: python-dynamic-execution
    eval(value)
    # ruleid: python-dynamic-execution
    exec(value)
    # ruleid: python-dynamic-execution
    subprocess.run(["example"], shell=True)
    # ok: python-dynamic-execution
    subprocess.run(["example"], shell=False)

def http():
    # ruleid: http-missing-timeout
    requests.get("https://example.invalid")
    # ok: http-missing-timeout
    requests.get("https://example.invalid", timeout=5)

# ruleid: ai-provider-sdk
import openai
# ok: ai-provider-sdk
import json
