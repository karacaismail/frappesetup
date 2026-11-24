"""platform_core endpoints. Identity endpoints follow section 5 of the service contract."""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.identity import sign_out
from platform_core.identity.safe_errors import safe_errors
from platform_core.mobile.api import close_keycloak_session


# The signed logout token authorizes only the session claims it carries.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=300, seconds=60)
@safe_errors
def keycloak_backchannel_logout(logout_token: str | None = None) -> dict:
	"""Receives Keycloak's logout notice. The token is verified with `oidc_verify`; matching sessions are closed.

	The phone client sends its notice here too, so a phone session ends at once (G-163).
	"""
	return sign_out.handle_logout_token(logout_token, close_mobile_session=close_keycloak_session)
