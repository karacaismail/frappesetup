"""Verify external MCP tokens and check the issuer's current session state."""

import json
import re
from dataclasses import dataclass, field
from time import time
from typing import NoReturn
from urllib.parse import urlencode, urlsplit

import frappe
from oidc_verify import JwksUnavailable, TokenError, verify_access_token

from platform_core.identity import anonymization, helpers, jwks, site_settings
from platform_core.identity.exceptions import KeycloakKeysUnavailable, ServiceTokenRejected
from platform_core.identity.mcp_introspection import fetch_introspection

MCP_PATH = "/api/method/platform_core.api.ai.mcp"
MCP_SCOPE = "mcp"
MAX_LIFETIME_SECONDS = 300
_MAX_RESPONSE_BYTES = 64 * 1024
_INTROSPECTION_TIMEOUT = 3.0
_CLIENT_ID = re.compile(r"[A-Za-z0-9._~-]{1,128}")
_REALM = re.compile(r"[A-Za-z0-9_-]+")
_URL = re.compile(r"https://[A-Za-z0-9.\-:\[\]]+(?:/[A-Za-z0-9._~/-]*)?")


@dataclass(frozen=True)
class _Settings:
	resource: str
	issuer: str
	jwks_url: str
	introspection_url: str
	client_ids: frozenset[str]
	introspection_secret: str = field(repr=False)


def _https_url(value: object) -> bool:
	if not isinstance(value, str) or len(value) > 2048 or not _URL.fullmatch(value):
		return False
	try:
		address = urlsplit(value)
		port = address.port
	except ValueError:
		return False
	return bool(address.hostname) and port != 0


def _settings() -> _Settings | None:
	conf = frappe.conf
	enabled = conf.get("mcp_oauth_enabled")
	if type(enabled) not in (int, bool) or enabled != 1:
		return None

	resource = conf.get("mcp_oauth_resource")
	public_url = conf.get("keycloak_public_url")
	internal_url = conf.get("keycloak_internal_url") or public_url
	realm = site_settings.realm()
	client_ids = conf.get("mcp_oauth_client_ids")
	secret = conf.get("mcp_oauth_introspection_secret")
	if (
		not _https_url(resource)
		or urlsplit(resource).path != MCP_PATH
		or not _https_url(public_url)
		or not _https_url(internal_url)
		or not isinstance(realm, str)
		or not _REALM.fullmatch(realm)
		or not isinstance(client_ids, list)
		or not client_ids
		or any(
			not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id) for client_id in client_ids
		)
		or not isinstance(secret, str)
		or not secret
	):
		return None

	return _Settings(
		resource=resource,
		issuer=helpers.issuer_url(public_url, realm),
		jwks_url=helpers.jwks_url(internal_url, realm),
		introspection_url=helpers.token_url(internal_url, realm) + "/introspect",
		client_ids=frozenset(client_ids),
		introspection_secret=secret,
	)


def mcp_oauth_config() -> dict | None:
	"""Return only public OAuth discovery settings when fully configured."""
	settings = _settings()
	if settings is None:
		return None
	return {"resource": settings.resource, "issuer": settings.issuer}


def verify_mcp_token(token: str) -> dict:
	"""Resolve an enabled linked identity and its live session without changing the request user."""
	settings = _settings()
	if settings is None or not isinstance(token, str) or len(token) > helpers.MAX_TOKEN_LENGTH:
		_reject()
	try:
		claims = verify_access_token(
			token,
			cache=jwks.jwks_cache(settings.jwks_url),
			issuer=settings.issuer,
			audience=settings.resource,
			allowed_azp=settings.client_ids,
			leeway=0,
		)
	except TokenError as error:
		_reject("expired" if error.code == "expired" else "invalid_token")
	except JwksUnavailable:
		_unavailable()

	# A matching audience can also come from Keycloak's authorization-code fallback.
	# This signed claim proves that the current token request supplied the resource.
	if claims.get("mcp_resource") != settings.resource:
		_reject()

	issued_at = claims.get("iat")
	expires_at = claims.get("exp")
	if type(issued_at) is not int or type(expires_at) is not int:
		_reject()
	if issued_at > time() or not 0 < expires_at - issued_at <= MAX_LIFETIME_SECONDS:
		_reject()

	scope = claims.get("scope")
	scopes = scope.split(" ") if isinstance(scope, str) else []
	subject = claims.get("sub")
	session_id = claims.get("sid")
	if (
		MCP_SCOPE not in scopes
		or "offline_access" in scopes
		or not isinstance(subject, str)
		or not subject
		or subject.strip() != subject
		or not isinstance(session_id, str)
		or not helpers.SESSION_ID_RE.fullmatch(session_id)
	):
		_reject()

	if anonymization.is_deleted(settings.issuer, subject):
		_reject()
	account = frappe.db.get_value(
		"PLT Identity Link", {"issuer": settings.issuer, "subject": subject}, "user"
	)
	if (
		not account
		or account in anonymization.PROTECTED_USERS
		or not frappe.db.get_value("User", account, "enabled")
	):
		_reject()

	client_id = claims["azp"]
	_verify_live_session(token, settings, subject=subject, session_id=session_id, client_id=client_id)
	if expires_at <= time():
		_reject("expired")
	return {
		"account": account,
		"issuer": settings.issuer,
		"subject": subject,
		"session_id": session_id,
		"resource": settings.resource,
		"client_id": client_id,
		"issued_at": issued_at,
		"expires_at": expires_at,
		"scopes": scopes,
	}


def _verify_live_session(
	token: str, settings: _Settings, *, subject: str, session_id: str, client_id: str
) -> None:
	# Keycloak checks the introspecting client against aud. Its confidential client ID is the resource URL.
	form = {
		"client_id": settings.resource,
		"client_secret": settings.introspection_secret,
		"token_type_hint": "access_token",
		"token": token,
	}
	try:
		body = fetch_introspection(
			settings.introspection_url,
			urlencode(form).encode("ascii"),
			timeout=_INTROSPECTION_TIMEOUT,
			max_bytes=_MAX_RESPONSE_BYTES,
		)
		result = json.loads(body)
	except (OSError, RecursionError, ValueError):
		_unavailable()

	if not isinstance(result, dict) or type(result.get("active")) is not bool:
		_unavailable()
	# The allowlist contains public clients with service grants disabled. Also reject Keycloak's
	# built-in service account usernames even if an operator misconfigures a client in that list.
	username = result.get("username")
	if (
		not result["active"]
		or result.get("sub") != subject
		or result.get("sid") != session_id
		or result.get("client_id") != client_id
		or not isinstance(username, str)
		or not username
		or username.startswith("service-account-")
	):
		_reject()


def _reject(reason: str = "invalid_token") -> NoReturn:
	error = ServiceTokenRejected(frappe._("MCP token rejected.", context="platform_core.identity"))
	error.reason = reason
	raise error from None


def _unavailable() -> NoReturn:
	raise KeycloakKeysUnavailable(
		frappe._("MCP identity provider unavailable.", context="platform_core.identity")
	) from None
