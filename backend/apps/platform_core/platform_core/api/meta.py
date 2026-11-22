"""HTTP entry point for effective DocType metadata."""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.shell.http import conditional_response, require_session
from platform_core.shell.metadata import compact_metadata
from platform_core.shell.metadata import get_doctype as read_doctype
from platform_core.shell.metadata_policy import validate_mobile_policy as check_mobile_policy
from platform_core.shell.request_policy import BootstrapQuery, MetadataQuery, validate_query


# The shared metadata function authorizes the DocType for HTTP and in-process callers.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=240, seconds=60, user_based=True, ip_based=False, methods=["GET"])
def get_doctype(doctype: str = "", surface: str = "web") -> dict | None:
	"""Read this site's real definition with the current user's field permissions."""
	user = require_session()
	validate_query(MetadataQuery)
	payload = read_doctype(doctype, user, surface=surface)
	return conditional_response(payload, user, compact_metadata)


@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
def validate_mobile_policy() -> dict:
	"""Check the site's metadata configuration for a System Manager."""
	frappe.only_for("System Manager", message=True)
	validate_query(BootstrapQuery)
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return check_mobile_policy()
