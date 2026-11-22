"""platform_core endpoints. This file belongs to the platform-core-kimlik task (docs/sozlesmeler.md, section 5)."""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.kimlik import sign_out
from platform_core.kimlik.safe_errors import safe_errors


# The signed logout token authorizes only the session claims it carries.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=300, seconds=60)
@safe_errors
def keycloak_backchannel_logout(logout_token: str | None = None) -> dict:
	"""Receives Keycloak's logout notice. The token is verified with `oidc_verify`; matching sessions are closed."""
	return sign_out.handle_logout_token(logout_token)
