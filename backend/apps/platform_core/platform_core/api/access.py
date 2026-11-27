"""Access rule endpoints. The business rule is in the `platform_core.access` module.

Contract: `backend/contracts/platform_core-access.openapi.yaml`.
"""

import frappe
from frappe import _
from frappe.permissions import is_system_user

from platform_core.access import explain, field_level, permission_log, tenant_admin


@frappe.whitelist(methods=["GET"])
def explain_permission(doctype: str, name: str, ptype: str = "read", user: str | None = None) -> dict:
	"""Explains the reason for the permission on a record. Changes no record.

	A Website User calls it only with the “Tenant Admin” role (G-62). Other portal users do not.
	"""
	if not is_system_user() and tenant_admin.ROLE not in frappe.get_roles():
		frappe.throw(_("No permission to explain permissions."), frappe.PermissionError)
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


@frappe.whitelist(methods=["GET"])
def list_role_permissions(doctype: str) -> dict:
	"""The role permission rows of a type (G-62). “System Manager” and “Tenant Admin” only."""
	return tenant_admin.list_role_permissions(doctype)


@frappe.whitelist(methods=["POST"])
def set_role_permission(
	doctype: str, role: str, permissions: dict, permlevel: int = 0, if_owner: int = 0
) -> dict:
	"""Creates or changes the permission row of a role on a type (G-62).

	“System Manager” and “Tenant Admin” only. A “Tenant Admin” cannot touch the two protected roles.
	"""
	if isinstance(permissions, str):
		permissions = frappe.parse_json(permissions)
	return tenant_admin.set_role_permission(doctype, role, permissions, permlevel, if_owner)


@frappe.whitelist(methods=["POST"])
def remove_role_permission(doctype: str, role: str, permlevel: int = 0, if_owner: int = 0) -> dict:
	"""Deletes the permission row of a role on a type (G-62). Same callers as `set_role_permission`."""
	return tenant_admin.remove_role_permission(doctype, role, permlevel, if_owner)


@frappe.whitelist(methods=["GET"])
def list_permission_logs(
	for_doctype: object = None, for_document: object = None, start: object = 0, page_length: object = None
) -> dict:
	"""A page of Permission Log rows, the newest first (G-62, G-98).

	“System Manager” and “Tenant Admin” only. Unknown query fields are refused.
	"""
	unknown = sorted(set(frappe.form_dict) - {"for_doctype", "for_document", "start", "page_length", "cmd"})
	if unknown:
		frappe.throw(_("Unknown field: {0}").format(", ".join(unknown)), permission_log.InvalidInput)
	return permission_log.list_permission_logs(for_doctype, for_document, start, page_length)
