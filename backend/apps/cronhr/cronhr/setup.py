"""Require the access engine before syncing CronHR permissions."""

import frappe
from frappe import _


def require_access_engine():
	query_hooks = frappe.get_hooks("permission_query_conditions", {}).get("*", [])
	document_hooks = frappe.get_hooks("has_permission", {}).get("*", [])
	if (
		"platform_core.erisim.hooks.query_conditions" not in query_hooks
		or "platform_core.erisim.hooks.has_permission" not in document_hooks
		or not frappe.db.exists("DocType", "Access Rule")
	):
		frappe.throw(_("Install Platform Core with Access Rule before syncing CronHR."))
