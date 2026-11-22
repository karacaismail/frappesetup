"""Public functions of the `kimlik` module for other modules (module boundary: `platform_core.kimlik.api`).

Mobile endpoints (platform-core-mobil) authenticate with a Keycloak access token of the mobile client.
The `auth_hooks` entry `service_token.validate` calls `authenticate_mobile_request()` for paths under
`MOBILE_PATH_PREFIX`; on success `frappe.local.mobile_identity` describes the caller (AU-3, AU-4, AU-5).
"""

import re

import frappe
from frappe import _

from platform_core.identity import helpers, jwks, site_settings
from platform_core.identity.exceptions import KeycloakKeysUnavailable, ServiceTokenRejected
from platform_core.identity.mcp_tokens import mcp_oauth_config, verify_mcp_token

LEEWAY = 30
MOBILE_SCOPE = "mobile"
LINK = "PLT Identity Link"
DEFAULT_MOBILE_AZP = ("mobile",)
INSTALLATION_HEADER = "X-Platform-Installation"
INSTALLATION_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


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
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format(error.code))
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		jwks.report_keys_unavailable(settings.jwks_url)
		frappe.throw(
			_("Identity provider keys are not available.", context="platform_core.identity"),
			KeycloakKeysUnavailable,
		)

	scopes = str(claims.get("scope") or "").split()
	if MOBILE_SCOPE not in scopes:
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format("missing_scope"))
	subject = claims.get("sub")
	if not isinstance(subject, str) or not subject.strip():
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format("malformed"))
	from platform_core.identity import anonymization

	# M-2: one rule for every way in. A deleted identity is refused here as in sign-in.
	if anonymization.is_deleted(settings.issuer, subject.strip()):
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format("deleted_identity"))
	user = frappe.db.get_value(LINK, {"issuer": settings.issuer, "subject": subject.strip()}, "user")
	if not user:
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format("unknown_identity"))
	if not frappe.db.get_value("User", user, "enabled"):
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format("user_disabled"))
	sid = claims.get("sid") if helpers.is_session_id(claims.get("sid")) else ""
	auth_time = claims.get("auth_time")
	# Contract section 3: without an integer auth_time the request is not a phone request.
	if type(auth_time) is not int:
		_refuse(_("Mobile token rejected: {0}", context="platform_core.identity").format("missing_auth_time"))
	issued_at = claims.get("iat")
	# docs/sozlesmeler.md section 3, phone identity: account, scope, site, installation and sid are text,
	# auth_time is the integer token claim.
	# issuer, subject and iat are read in addition by the mobile module (mobil/request.py).
	return {
		"account": user,
		"scope": MOBILE_SCOPE,
		"site": frappe.local.site,
		"installation": _installation(),
		"sid": sid,
		"issuer": settings.issuer,
		"subject": subject.strip(),
		"iat": issued_at if type(issued_at) is int else 0,
		"auth_time": auth_time,
		"azp": claims.get("azp"),
		"expires_at": claims.get("exp"),
	}


def _installation() -> str:
	"""Installation id from the `X-Platform-Installation` header. Text in a fixed shape, otherwise empty.

	docs/sozlesmeler.md section 3 (phone identity): the header is `X-Platform-Installation`, 1 to 128
	characters of `A-Z`, `a-z`, `0-9`, `_` and `-`. A missing or malformed header gives an empty text.
	The value carries no authority; the mobile module checks the installation against its own records.
	"""
	value = frappe.get_request_header(INSTALLATION_HEADER) or ""
	return value if INSTALLATION_PATTERN.fullmatch(value) else ""


def authenticate_mobile_request(token: str) -> None:
	"""Sets the request user from a mobile token and records `frappe.local.mobile_identity`."""
	identity = verify_mobile_token(token)
	form_dict = frappe.local.form_dict
	frappe.set_user(identity["account"])
	frappe.local.form_dict = form_dict
	frappe.local.mobile_identity = identity


def _refuse(message: str) -> None:
	frappe.throw(message, ServiceTokenRejected)
