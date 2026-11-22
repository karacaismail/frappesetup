"""Helpers that do not depend on Frappe. Their tests need no database."""

import re
from urllib.parse import urlencode

PROVIDER = "keycloak"
PROVIDER_BASE_NAME = "Keycloak"
IDENTITY_API_PREFIX = "/api/method/platform_core.api.identity."
SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
# G-11: only characters that are safe inside an HTML attribute and a URL path, query and fragment.
_SAFE_REDIRECT = re.compile(r"/[A-Za-z0-9\-._~/?#@!$&()*+,;=%:\[\]]*")
MAX_REDIRECT_LENGTH = 2048
MAX_GUEST_BODY_BYTES = 16 * 1024
MAX_TOKEN_LENGTH = 8192
MAX_CODE_LENGTH = 4096
MAX_STATE_LENGTH = 255
MOBILE_PATH_PREFIX = "/api/method/platform_core.api.mobile.v1_"


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
) -> str:
	"""Keycloak RP-initiated logout address."""
	params = {"client_id": client_id, "post_logout_redirect_uri": post_logout_redirect_uri}
	return realm_url(public_url, realm) + "/protocol/openid-connect/logout?" + urlencode(params)


def is_safe_redirect(path: object) -> bool:
	"""Only a same-origin relative path: starts with `/`, not with `//` or `/\\`, no control characters."""
	if not isinstance(path, str) or not path or len(path) > MAX_REDIRECT_LENGTH:
		return False
	if not path.startswith("/") or path.startswith("//") or path.startswith("/\\"):
		return False
	if "\\" in path or _CONTROL_OR_SPACE.search(path):
		return False
	return bool(_SAFE_REDIRECT.fullmatch(path))


def is_session_id(value: object) -> bool:
	"""Keycloak 26.8.2 generates Base64url session IDs. Keep accepting UUIDs."""
	return isinstance(value, str) and SESSION_ID_RE.fullmatch(value) is not None


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


CALLBACK_PATH = "/api/method/platform_core.api.auth.keycloak_callback"
_SLASHES = re.compile(r"/+")


def normalize_path(path: str) -> str:
	"""Normalises a request path the way Frappe's website resolver does: repeated slashes, `.`/`..`,
	trailing slash and a `.html` suffix are removed (frappe/website/path_resolver.py:34, :206)."""
	import posixpath

	collapsed = _SLASHES.sub("/", path or "/")
	normalized = posixpath.normpath(collapsed)
	if normalized.endswith(".html"):
		normalized = normalized[: -len(".html")]
	normalized = normalized.rstrip("/")
	return normalized or "/"


def sha256_hex(value: str) -> str:
	import hashlib

	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def code_challenge(code_verifier: str) -> str:
	"""PKCE S256 challenge (RFC 7636, section 4.2)."""
	import base64
	import hashlib

	digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
	return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(
	public_url: str,
	realm: str,
	client_id: str,
	redirect_uri: str,
	state: str,
	nonce: str,
	challenge: str,
	prompt: str | None = None,
) -> str:
	params = {
		"client_id": client_id,
		"redirect_uri": redirect_uri,
		"response_type": "code",
		"scope": "openid",
		"state": state,
		"nonce": nonce,
		"code_challenge": challenge,
		"code_challenge_method": "S256",
	}
	if prompt:
		params["prompt"] = prompt
	return realm_url(public_url, realm) + "/protocol/openid-connect/auth?" + urlencode(params)


def token_url(base_url: str, realm: str) -> str:
	return realm_url(base_url, realm) + "/protocol/openid-connect/token"
