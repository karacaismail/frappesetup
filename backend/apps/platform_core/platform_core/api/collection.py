"""HTTP entry point for collection summaries."""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.shell.collection import read_query, read_summary
from platform_core.shell.http import require_session


# read_summary applies DocType and field permissions before the permission-aware list query.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=120, seconds=60, user_based=True, ip_based=False, methods=["GET"])
def group_summary() -> dict:
	"""Return counts and an optional numeric statistic for visible records."""
	user = require_session()
	return read_summary(read_query(), user)
