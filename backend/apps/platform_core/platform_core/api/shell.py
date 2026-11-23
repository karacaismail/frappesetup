"""HTTP entry point for shell bootstrap."""

from pathlib import Path

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

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


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=120, seconds=60, methods=["GET"])
def record_preview_image() -> Response:
	"""Serve the same static card for every record route."""
	path = Path(frappe.get_app_path("platform_core", "shell", "record_preview.png"))
	return Response(
		path.read_bytes(),
		mimetype="image/png",
		headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"},
	)
