"""Access rule endpoints. The business rule is in the `platform_core.access` module.

Contract: `backend/contracts/platform_core-access.openapi.yaml`.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.access import explain, field_level, record_links


@frappe.whitelist(methods=["GET"])
def explain_permission(doctype: str, name: str, ptype: str = "read", user: str | None = None) -> dict:
	"""Explains the reason for the permission on a record. Changes no record."""
	if not doctype or not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No permission to read this document type."), frappe.PermissionError)
	return explain.explain(doctype, name, ptype, user)


@frappe.whitelist(methods=["GET"])
def get_access_summary(doctype: str) -> dict:
	"""Returns the rule scopes of the session user in a document type."""
	if not doctype or not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No permission to read this document type."), frappe.PermissionError)
	return explain.summary(doctype)


@frappe.whitelist(methods=["POST"])
def set_field_level(doctype: str, fieldname: str, permlevel: int) -> dict:
	"""Changes the permission level of a field. “System Manager” only."""
	if not frappe.has_permission("Property Setter", "create"):
		frappe.throw(_("No permission to change field levels."), frappe.PermissionError)
	return field_level.set_field_level(doctype, fieldname, permlevel)


@frappe.whitelist(methods=["POST"])
def set_level_access(doctype: str, role: str, permlevel: int, read: bool, write: bool) -> dict:
	"""Gives a role read and write permission at a permission level. “System Manager” only."""
	if not frappe.has_permission("Custom DocPerm", "write"):
		frappe.throw(_("No permission to change role permissions."), frappe.PermissionError)
	return field_level.set_level_access(doctype, role, permlevel, read, write)


# The access service checks the session user against the target record.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def create_record_link(doctype: str, name: str) -> dict:
	return record_links.create(doctype, name)


# The access service checks the session user against the target record.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def open_record_link(token: str) -> dict:
	return record_links.open_link(token)


# The access service checks the session user against the target record.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def revoke_record_link(link_id: str) -> dict:
	return record_links.revoke(link_id)


# The service stores a private request. It returns no record data and grants no permission.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=10, seconds=60, user_based=True, ip_based=False, methods=["POST"])
def request_record_access(token: str | None = None, doctype: str = "", name: str = "") -> dict:
	return record_links.request_access(token, doctype, name)
