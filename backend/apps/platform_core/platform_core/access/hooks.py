"""Functions bound to the permission hooks of Frappe.

The `hooks.py` file binds these functions to all document types with the `"*"` key.
In Frappe 16, access is denied if the `has_permission` hook returns `None`
(`frappe/permissions.py:497`). So the function always returns `True` or `False`.
"""

import frappe

from platform_core.access import engine, files, reports, rules


def has_permission(doc, ptype: str | None = None, user: str | None = None, debug: bool = False) -> bool:
	"""The single record hook. The engine only narrows: `True` does not grant permission, the role permission is checked separately."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if doc.doctype == reports.PREPARED_REPORT:
		# Prepared Report is switched off for reports that touch governed data.
		return not reports.touches_governed(doc.report_name)
	if doc.doctype == "File" and doc.get("attached_to_doctype") == reports.PREPARED_REPORT:
		return not reports.prepared_report_closed(doc.get("attached_to_name"))
	if not rules.is_governed(doc.doctype):
		return True
	return engine.decide(doc, ptype, user)


def query_conditions(user: str | None = None, doctype: str | None = None):
	"""The list hook. Adds no condition for a document type that is not governed."""
	user = user or frappe.session.user
	if user == "Administrator" or not doctype:
		return None
	if doctype == files.FILE:
		# An attachment of a governed record is listed only if the record passes the list rule (G-121).
		return files.list_criterion(user)
	return engine.list_criterion(doctype, user)
