"""HTTP entry point for effective DocType metadata."""

import frappe

from platform_core.kabuk.metadata import get_doctype as read_doctype


@frappe.whitelist(methods=["GET"])
def get_doctype(doctype: str) -> dict | None:
	"""Read this site's real definition with the current user's field permissions."""
	return read_doctype(doctype)
