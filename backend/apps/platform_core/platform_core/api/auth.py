"""Sign-in and sign-out endpoints. Business rules live in `platform_core.kimlik`; this file stays thin."""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.kimlik import provider_setup, sign_in, sign_out


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60)
def get_login_url(redirect_to: str | None = None) -> dict:
	"""Builds the Keycloak sign-in address. `state` is generated on the server. `redirect_to` must be a relative path."""
	return sign_in.build_login_url(redirect_to)


@frappe.whitelist(methods=["POST"])
def logout() -> dict:
	"""Closes the Frappe session and returns the Keycloak logout address."""
	return sign_out.logout_current_session()


@frappe.whitelist(methods=["POST"])
def setup_keycloak_login() -> dict:
	"""Creates or updates the Keycloak “Social Login Key” from site settings. System Manager only."""
	frappe.only_for("System Manager")
	return provider_setup.ensure_social_login_key()
