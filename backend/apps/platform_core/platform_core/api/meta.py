"""HTTP entry point for effective DocType metadata."""

import frappe

from platform_core.kabuk.http import require_session
from platform_core.kabuk.metadata import get_doctype as read_doctype


@frappe.whitelist(methods=["GET"])
def get_doctype(doctype: str) -> dict | None:
	"""Read this site's real definition with the current user's field permissions."""
	user = require_session()
	if not doctype.strip() or len(doctype) > 140:
		frappe.throw(frappe._("A valid DocType name is required."), frappe.ValidationError)
	if frappe.get_meta(doctype).istable:
		frappe.throw(frappe._("You cannot read this DocType."), frappe.PermissionError)
	if not frappe.has_permission(doctype, "read", user=user):
		frappe.throw(frappe._("You cannot read this DocType."), frappe.PermissionError)
	return read_doctype(doctype, user)
