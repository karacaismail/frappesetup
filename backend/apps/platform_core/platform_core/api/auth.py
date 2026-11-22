"""Sign-in and sign-out endpoints. The identity module implements the sign-in policy."""

from collections.abc import Callable
from functools import wraps

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.identity import provider_setup, sign_in, sign_out
from platform_core.identity.exceptions import InvalidRedirect, KeycloakLoginNotConfigured
from platform_core.identity.safe_errors import safe_errors


def _render_browser_rate_limit(function: Callable[..., None]) -> Callable[..., None]:
	@wraps(function)
	def wrapped(*args: object, **kwargs: object) -> None:
		try:
			return function(*args, **kwargs)
		except frappe.RateLimitExceededError:
			if frappe.form_dict.get("cmd") and not frappe.request.path.startswith("/api/"):
				# Legacy cmd dispatch builds its own JSON response and ignores the return value.
				frappe.local.response.update(http_status_code=429, exc_type="RateLimitExceededError")
				return
			accept = frappe.get_request_header("Accept") or ""
			if not accept.startswith("text") or "application/json" in accept or frappe.local.is_ajax:
				raise
			# Frappe's site-wide limiter cannot render an endpoint-level 429.
			frappe.respond_as_web_page(
				_("Sign-in failed", context="platform_core.identity"),
				_(
					"You hit the rate limit because of too many requests. Please try after sometime.",
					context="platform_core.identity",
				),
				http_status_code=429,
				indicator_color="red",
			)

	return wrapped


# The login routes validate browser state and never take a Frappe record selector. Session routes check the current session or role.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=20, seconds=60)
def get_login_url(redirect_to: str | None = None) -> dict:
	"""Builds the Keycloak sign-in address. `state` is generated on the server. `redirect_to` must be a relative path."""
	return sign_in.build_login_url(redirect_to)


# The login routes validate browser state and never take a Frappe record selector. Session routes check the current session or role.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: frappe-missing-permission
@_render_browser_rate_limit
@rate_limit(limit=20, seconds=60)
def start_login(redirect_to: str | None = None) -> None:
	"""Browser entry point of the sign-in: same work as `get_login_url`, then a 302 to Keycloak.
	The brand button on the tenant `/login` page links here."""
	try:
		result = sign_in.build_login_url(redirect_to)
	except (InvalidRedirect, KeycloakLoginNotConfigured) as error:
		frappe.respond_as_web_page(
			_("Sign-in failed", context="platform_core.identity"),
			str(error),
			http_status_code=error.http_status_code,
			indicator_color="red",
		)
		return
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = result["login_url"]


# The login routes validate browser state and never take a Frappe record selector. Session routes check the current session or role.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: frappe-missing-permission
@_render_browser_rate_limit
@rate_limit(limit=20, seconds=60)
@safe_errors
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
	except sign_in.SignInRefusedError as refusal:
		# Releases the identity lock at once (merge review E1). Nothing of a refused sign-in is kept.
		frappe.db.rollback()
		frappe.respond_as_web_page(
			_("Sign-in failed", context="platform_core.identity"),
			refusal.message,
			http_status_code=refusal.status,
			indicator_color="red",
		)
		return
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = target


# The login routes validate browser state and never take a Frappe record selector. Session routes check the current session or role.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=20, seconds=60, user_based=True)
def logout() -> dict:
	"""Closes the Frappe session and returns the Keycloak logout address."""
	return sign_out.logout_current_session()


# The login routes validate browser state and never take a Frappe record selector. Session routes check the current session or role.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=10, seconds=60, user_based=True)
def setup_keycloak_login() -> dict:
	"""Creates or updates the Keycloak “Social Login Key” from site settings. System Manager only."""
	frappe.only_for("System Manager")
	return provider_setup.ensure_social_login_key()
