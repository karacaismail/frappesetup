"""Helpers that do not depend on Frappe. Their tests need no database."""

import re
from urllib.parse import urlencode

PROVIDER = "keycloak"
PROVIDER_BASE_NAME = "Keycloak"
LOGIN_CALLBACK_PATH = "/api/method/frappe.integrations.oauth2_logins.login_via_keycloak"
IDENTITY_API_PREFIX = "/api/method/platform_core.api.identity."
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
MAX_REDIRECT_LENGTH = 2048


def realm_url(base_url: str, realm: str) -> str:
	return f"{base_url.rstrip('/')}/realms/{realm}"


def issuer_url(public_url: str, realm: str) -> str:
	"""The `iss` claim value (docs/sozlesmeler.md, section 2)."""
	return realm_url(public_url, realm)


def jwks_url(base_url: str, realm: str) -> str:
	return realm_url(base_url, realm) + "/protocol/openid-connect/certs"


def end_session_url(
	public_url: str,
	realm: str,
	client_id: str,
	post_logout_redirect_uri: str,
	id_token_hint: str | None = None,
) -> str:
	"""Keycloak RP-initiated logout address."""
	params = {"client_id": client_id, "post_logout_redirect_uri": post_logout_redirect_uri}
	if id_token_hint:
		params["id_token_hint"] = id_token_hint
	return realm_url(public_url, realm) + "/protocol/openid-connect/logout?" + urlencode(params)


def is_safe_redirect(path: object) -> bool:
	"""Only a same-origin relative path: starts with `/`, not with `//` or `/\\`, no control characters."""
	if not isinstance(path, str) or not path or len(path) > MAX_REDIRECT_LENGTH:
		return False
	if not path.startswith("/") or path.startswith("//") or path.startswith("/\\"):
		return False
	if "\\" in path or _CONTROL_OR_SPACE.search(path):
		return False
	return True


def is_session_id(value: object) -> bool:
	"""Keycloak `sid` is a UUID. Other characters could act as LIKE wildcards."""
	return isinstance(value, str) and bool(SESSION_ID_RE.match(value))


def session_marker(sid: str) -> str:
	"""Fragment searched in `tabSessions.sessiondata`. Frappe writes that JSON with `(",", ":")` separators."""
	return f'"keycloak_sid":"{sid}"'


def session_claims(claims: dict, issuer: str) -> dict:
	"""Keycloak details stored in the Frappe session record."""
	data = {"keycloak_iss": issuer, "keycloak_sub": claims.get("sub")}
	sid = claims.get("sid")
	if is_session_id(sid):
		data["keycloak_sid"] = sid
	return data


def email_verified(claims: dict) -> bool:
	value = claims.get("email_verified")
	if isinstance(value, bool):
		return value
	return isinstance(value, str) and value.strip().lower() == "true"
