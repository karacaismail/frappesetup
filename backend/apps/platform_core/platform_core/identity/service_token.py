"""Service token validation (`auth_hooks`). Rules: docs/sozlesmeler.md section 3, AU-3 and AU-5.

The hook runs on every request from `frappe.auth.validate_auth` (frappe/auth.py:755). A token is looked
for only on the service endpoints (`SERVICE_ENDPOINTS`) and on the mobile paths. Service endpoints are
matched first. A request already authenticated for the same route by an earlier hook is left alone.
Elsewhere the hook does nothing; Frappe then rejects a
request that carries a Bearer header while the user stays Guest (frappe/auth.py:649).
"""

import frappe
from frappe import _

from platform_core.identity import helpers, jwks, site_settings
from platform_core.identity.exceptions import KeycloakKeysUnavailable, ServiceTokenRejected

LEEWAY = 30
IDENTITY_ENDPOINTS = frozenset(
	helpers.IDENTITY_API_PREFIX + name
	for name in ("provision", "set_enabled", "change_email", "anonymize_user", "list_identities")
)
# Service endpoints of other modules that identity-sync calls with its service token (docs/sozlesmeler.md
# section 7). They are checked before the mobile path rule, so a service token is never read as a phone token.
OTHER_SERVICE_ENDPOINTS = frozenset(("/api/method/platform_core.api.mobile.revoke_user_installations",))
SERVICE_ENDPOINTS = IDENTITY_ENDPOINTS | OTHER_SERVICE_ENDPOINTS
CLAIMS_ATTR = "identity_service_claims"
# Service operations run as the administrator. The path and azp restrictions confine the token to these endpoints.
SERVICE_USER = "Administrator"


def validate() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None or request.method == "OPTIONS":
		return
	from platform_core.identity import api as identity_api

	service = request.path in SERVICE_ENDPOINTS
	mobile = not service and identity_api.is_mobile_path(request.path)
	if not service and not mobile:
		return
	parts = (frappe.get_request_header("Authorization") or "").split(" ", 1)
	if len(parts) != 2 or parts[0].lower() != "bearer":
		return
	token = parts[1].strip()
	if len(token) > helpers.MAX_TOKEN_LENGTH:
		_refuse(_("Service token rejected: {0}", context="platform_core.identity").format("malformed"))

	if frappe.form_dict.get("cmd"):
		_refuse(_("Service requests must not carry a cmd field.", context="platform_core.identity"))
	if frappe.session.user not in ("", "Guest"):
		# An earlier hook can authenticate this request without creating a browser session.
		# Only a server-side marker for this route can distinguish it from another login.
		login_manager = getattr(frappe.local, "login_manager", None)
		has_browser_session = request.cookies.get("sid") not in (None, "", "Guest") and getattr(
			login_manager, "user", "Guest"
		) not in (None, "", "Guest")
		if not has_browser_session and (
			(mobile and getattr(frappe.local, "mobile_identity", None))
			or (service and frappe.session.user == SERVICE_USER and getattr(frappe.local, CLAIMS_ATTR, None))
		):
			return
		_refuse(_("Service requests must not carry a session cookie.", context="platform_core.identity"))

	if mobile:
		identity_api.authenticate_mobile_request(token)
		return

	from oidc_verify import TokenError, verify_access_token

	settings = site_settings.get()
	try:
		claims = verify_access_token(
			token,
			cache=jwks.jwks_cache(settings.jwks_url),
			issuer=settings.issuer,
			audience=settings.client_id,
			allowed_azp=settings.service_azp,
			leeway=LEEWAY,
		)
	except TokenError as error:
		_refuse(_("Service token rejected: {0}", context="platform_core.identity").format(error.code))
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		jwks.report_keys_unavailable(settings.jwks_url)
		frappe.throw(
			_("Identity provider keys are not available.", context="platform_core.identity"),
			KeycloakKeysUnavailable,
		)

	# `frappe.set_user` resets `form_dict` (frappe/__init__.py:388); keep the request arguments.
	form_dict = frappe.local.form_dict
	frappe.set_user(SERVICE_USER)
	frappe.local.form_dict = form_dict
	setattr(frappe.local, CLAIMS_ATTR, claims)


def require_service(*azp: str) -> dict:
	"""Called inside an endpoint. 403 when there is no token or `azp` is not in the list."""
	claims = getattr(frappe.local, CLAIMS_ATTR, None)
	if not claims or claims.get("azp") not in azp:
		frappe.throw(
			_("This endpoint accepts only the {0} service token.", context="platform_core.identity").format(
				", ".join(azp)
			),
			frappe.PermissionError,
		)
	return claims


def _refuse(message: str) -> None:
	frappe.throw(message, ServiceTokenRejected)
