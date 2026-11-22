"""Sign-in and sign-out endpoints. Business rules live in `platform_core.kimlik`; this file stays thin."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.kimlik import provider_setup, sign_in, sign_out
from platform_core.kimlik.exceptions import InvalidRedirect, KeycloakLoginNotConfigured


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60)
def get_login_url(redirect_to: str | None = None) -> dict:
	"""Builds the Keycloak sign-in address. `state` is generated on the server. `redirect_to` must be a relative path."""
	return sign_in.build_login_url(redirect_to)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=20, seconds=60)
def start_login(redirect_to: str | None = None) -> None:
	"""Browser entry point of the sign-in: same work as `get_login_url`, then a 302 to Keycloak.
	The brand button on the tenant `/login` page links here."""
	try:
		result = sign_in.build_login_url(redirect_to)
	except (InvalidRedirect, KeycloakLoginNotConfigured) as error:
		frappe.respond_as_web_page(
			_("Sign-in failed"), str(error), http_status_code=error.http_status_code, indicator_color="red"
		)
		return
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = result["login_url"]


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=20, seconds=60)
def keycloak_callback(
	code: str | None = None,
	state: str | None = None,
	error: str | None = None,
	error_description: str | None = None,
) -> None:
	"""Keycloak redirect target. Consumes the state once, checks the browser cookie, exchanges the code with
	PKCE, verifies the ID token and opens the Frappe session. Answers with a redirect or an HTML error page."""
	try:
		target = sign_in.complete_callback(code, state, error)
	except sign_in.SignInRefused as refusal:
		frappe.respond_as_web_page(
			_("Sign-in failed"), refusal.message, http_status_code=refusal.status, indicator_color="red"
		)
		return
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = target


@frappe.whitelist(methods=["POST"])
def logout() -> dict:
	"""Closes the Frappe session and returns the Keycloak logout address."""
	return sign_out.logout_current_session()


@frappe.whitelist(methods=["POST"])
def setup_keycloak_login() -> dict:
	"""Creates or updates the Keycloak “Social Login Key” from site settings. System Manager only."""
	frappe.only_for("System Manager")
	return provider_setup.ensure_social_login_key()
