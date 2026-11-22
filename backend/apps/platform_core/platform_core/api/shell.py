"""HTTP entry point for shell bootstrap."""

import frappe

from platform_core.kabuk.bootstrap import get_bootstrap as read_bootstrap
from platform_core.kabuk.http import require_session


# No record selector is accepted. Identity comes from the session cookie, and
# the native Sidebar resolver checks permissions on every navigation target.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
def get_bootstrap() -> dict | None:
	"""Read the current user's installed applications and permitted navigation."""
	return read_bootstrap(require_session())
