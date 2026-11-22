"""Obtain Keycloak service tokens for outbound identity-sync calls."""

import json
import re
from ipaddress import ip_address
from threading import Lock
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import frappe

_TIMEOUT_SECONDS = 3
_MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
_BEARER = re.compile(r"[A-Za-z0-9._~+/-]+=*", re.ASCII)
_SITE_SERVICE_CLIENT = re.compile(r"site-[a-z0-9][a-z0-9-]*-service")
_REALM = re.compile(r"[A-Za-z0-9_-]+")


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		# The request carries credentials for the configured host only.
		return None


_OPENER = build_opener(_NoRedirect())
_LOCAL_OPENER = build_opener(ProxyHandler({}), _NoRedirect())
_cached_bearer = None
_cache_lock = Lock()


def development_http_allowed(address, local_service_host: str) -> bool:
	"""Permit direct development HTTP to loopback or the named Compose service."""
	if address.scheme != "http" or frappe.conf.get("developer_mode") not in (1, "1"):
		return False
	host = address.hostname
	if not host:
		return False
	# Validate the port before any credential or request is created.
	if address.port == 0:
		return False
	if host in ("localhost", local_service_host):
		return True
	try:
		return ip_address(host).is_loopback
	except ValueError:
		return False


def _token_url() -> str:
	base = frappe.conf.get("keycloak_internal_url") or frappe.conf.get("keycloak_public_url")
	realm = frappe.conf.get("keycloak_realm") or "platform"
	if (
		not isinstance(base, str)
		or any(ord(char) <= 32 or ord(char) == 127 for char in base)
		or not isinstance(realm, str)
		or not _REALM.fullmatch(realm)
	):
		raise ValueError("Invalid Keycloak service URL")
	address = urlsplit(base)
	if (
		(address.scheme != "https" and not development_http_allowed(address, "identity.localhost"))
		or not address.hostname
		or address.username is not None
		or address.query
		or address.fragment
	):
		raise ValueError("Invalid Keycloak service URL")
	return f"{base.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"


def identity_sync_bearer() -> str:
	global _cached_bearer
	url = _token_url()
	client_id = frappe.conf.get("keycloak_service_client_id")
	client_secret = frappe.conf.get("keycloak_service_client_secret")
	if (
		not isinstance(client_id, str)
		or not _SITE_SERVICE_CLIENT.fullmatch(client_id)
		or client_id.removesuffix("-service") != frappe.conf.get("keycloak_client_id")
		or not isinstance(client_secret, str)
		or not client_secret
	):
		raise ValueError("Missing identity-sync service credentials")

	cache_key = (url, client_id, client_secret)
	cached = _cached_bearer
	now = monotonic()
	if cached is not None:
		key, token, expires_at = cached
		if key == cache_key and now < expires_at:
			return token

	form = {
		"grant_type": "client_credentials",
		"client_id": client_id,
		"client_secret": client_secret,
		"scope": "aud-identity-sync",
	}
	req = Request(
		url,
		data=urlencode(form).encode("ascii"),
		headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
		method="POST",
	)
	try:
		opener = _LOCAL_OPENER if urlsplit(url).scheme == "http" else _OPENER
		with opener.open(req, timeout=_TIMEOUT_SECONDS) as response:
			if response.status != 200:
				raise ValueError("Identity-sync token request failed")
			body = response.read(_MAX_TOKEN_RESPONSE_BYTES + 1)
	except HTTPError as error:
		error.close()
		raise
	if len(body) > _MAX_TOKEN_RESPONSE_BYTES:
		raise ValueError("Identity-sync token response is too large")
	payload = json.loads(body)
	token = payload.get("access_token") if isinstance(payload, dict) else None
	if not isinstance(token, str) or not _BEARER.fullmatch(token):
		raise ValueError("Invalid identity-sync service token")
	expires_in = payload.get("expires_in")
	if type(expires_in) is int and expires_in > 5:
		with _cache_lock:
			_cached_bearer = (cache_key, token, now + min(expires_in, 86400) - 5)
	return token


def invalidate_identity_sync_bearer(rejected: str) -> None:
	"""Evict only the rejected bearer so a concurrent refresh stays cached."""
	global _cached_bearer
	with _cache_lock:
		if _cached_bearer is not None and _cached_bearer[1] == rejected:
			_cached_bearer = None
