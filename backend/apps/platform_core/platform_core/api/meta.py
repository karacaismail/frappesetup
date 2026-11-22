"""HTTP entry point for effective DocType metadata."""

import frappe

from platform_core.kabuk.http import conditional_response, require_session
from platform_core.kabuk.metadata import get_doctype as read_doctype


# The shared metadata function authorizes the DocType for HTTP and in-process callers.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
def get_doctype(doctype: str, surface: str = "web") -> dict | None:
	"""Read this site's real definition with the current user's field permissions."""
	user = require_session()
	payload = read_doctype(doctype, user, surface=surface)
	return conditional_response(payload, user, payload["perm_version"])
