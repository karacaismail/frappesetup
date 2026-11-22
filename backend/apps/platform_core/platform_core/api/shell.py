"""HTTP entry point for shell bootstrap."""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.shell.bootstrap import compact_bootstrap
from platform_core.shell.bootstrap import get_bootstrap as read_bootstrap
from platform_core.shell.http import conditional_response, require_session
from platform_core.shell.request_policy import BootstrapQuery, validate_query


# No record selector is accepted. Identity comes from the session cookie, and
# the native Sidebar resolver checks permissions on every navigation target.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=120, seconds=60, user_based=True, ip_based=False, methods=["GET"])
def get_bootstrap() -> dict | None:
	"""Read the current user's installed applications and permitted navigation."""
	user = require_session()
	validate_query(BootstrapQuery)
	payload = read_bootstrap(user)
	return conditional_response(payload, user, compact_bootstrap)
