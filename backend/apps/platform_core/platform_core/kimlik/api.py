"""Public functions of the `kimlik` module for other modules (module boundary: `platform_core.kimlik.api`).

Mobile endpoints (platform-core-mobil) authenticate with a Keycloak access token of the mobile client.
The `auth_hooks` entry `service_token.validate` calls `authenticate_mobile_request()` for paths under
`MOBILE_PATH_PREFIX`; on success `frappe.local.mobile_identity` describes the caller (AU-3, AU-4, AU-5).
"""

import frappe
from frappe import _

from platform_core.kimlik import helpers, jwks, site_settings
from platform_core.kimlik.exceptions import KeycloakKeysUnavailable, ServiceTokenRejected

LEEWAY = 30
MOBILE_SCOPE = "mobile"
LINK = "Platform Identity Link"
DEFAULT_MOBILE_AZP = ("mobile",)


def mobile_azp() -> frozenset[str]:
	"""Keycloak client ids allowed to call mobile endpoints (site setting `kimlik_mobil_azp`)."""
	value = frappe.conf.get("kimlik_mobil_azp") or list(DEFAULT_MOBILE_AZP)
	if isinstance(value, str):
		value = [value]
	return frozenset(value)


def is_mobile_path(path: str) -> bool:
	return path.startswith(helpers.MOBILE_PATH_PREFIX)


def verify_mobile_token(token: str) -> dict:
	"""Verifies a mobile access token and resolves the Frappe user. Raises `ServiceTokenRejected` (401).

	Checks: RS256 signature, `iss`, single `aud` (this site's client), `azp` in the mobile list, `exp`
	with 30 s leeway, the `mobile` scope, an existing `(iss, sub)` link and an enabled user.
	"""
	from oidc_verify import TokenError, verify_access_token

	settings = site_settings.get()
	try:
		claims = verify_access_token(
			token,
			cache=jwks.jwks_cache(settings.jwks_url),
			issuer=settings.issuer,
			audience=settings.client_id,
			allowed_azp=mobile_azp(),
			leeway=LEEWAY,
		)
	except TokenError as error:
		_refuse(_("Mobile token rejected: {0}").format(error.code))
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		jwks.report_keys_unavailable(settings.jwks_url)
		frappe.throw(_("Identity provider keys are not available."), KeycloakKeysUnavailable)

	scopes = str(claims.get("scope") or "").split()
	if MOBILE_SCOPE not in scopes:
		_refuse(_("Mobile token rejected: {0}").format("missing_scope"))
	subject = claims.get("sub")
	if not isinstance(subject, str) or not subject.strip():
		_refuse(_("Mobile token rejected: {0}").format("malformed"))
	user = frappe.db.get_value(LINK, {"issuer": settings.issuer, "subject": subject.strip()}, "user")
	if not user:
		_refuse(_("Mobile token rejected: {0}").format("unknown_identity"))
	if not frappe.db.get_value("User", user, "enabled"):
		_refuse(_("Mobile token rejected: {0}").format("user_disabled"))
	sid = claims.get("sid") if helpers.is_session_id(claims.get("sid")) else None
	return {
		"user": user,
		"issuer": settings.issuer,
		"subject": subject.strip(),
		"sid": sid,
		"azp": claims.get("azp"),
		"scope": scopes,
		"expires_at": claims.get("exp"),
	}


def authenticate_mobile_request(token: str) -> None:
	"""Sets the request user from a mobile token and records `frappe.local.mobile_identity`."""
	identity = verify_mobile_token(token)
	form_dict = frappe.local.form_dict
	frappe.set_user(identity["user"])
	frappe.local.form_dict = form_dict
	frappe.local.mobile_identity = identity


def _refuse(message: str) -> None:
	frappe.throw(message, ServiceTokenRejected)
