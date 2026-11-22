"""Deliver committed mobile session revocations to identity-sync."""

import json
import re
from http.client import HTTPException
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import frappe

_TIMEOUT_SECONDS = 3
_MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
_BEARER = re.compile(r"[A-Za-z0-9._~+/-]+=*", re.ASCII)
_DELIVERY_ERRORS = (HTTPException, OSError, ValueError, RecursionError)


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		# The request carries credentials for the configured host only.
		return None


_OPENER = build_opener(_NoRedirect())
_cached_bearer = None


def _configured_url(key, *, origin_only=False):
	value = frappe.conf.get(key)
	if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
		raise ValueError("Invalid identity-sync URL")
	address = urlsplit(value)
	if (
		address.scheme != "https"
		or not address.hostname
		or address.username is not None
		or address.query
		or address.fragment
		or (origin_only and address.path not in ("", "/"))
	):
		raise ValueError("Invalid identity-sync URL")
	return value.rstrip("/") if origin_only else value


def _service_bearer():
	global _cached_bearer
	url = _configured_url("mobile_identity_sync_token_url")
	client_id = frappe.conf.get("keycloak_service_client_id")
	client_secret = frappe.conf.get("keycloak_service_client_secret")
	if not all(isinstance(value, str) and value for value in (client_id, client_secret)):
		raise ValueError("Missing identity-sync service credentials")
	if client_id == frappe.conf.get("keycloak_client_id"):
		raise ValueError("The browser client cannot request identity-sync service tokens")

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
	with _OPENER.open(req, timeout=_TIMEOUT_SECONDS) as response:
		if response.status != 200:
			raise ValueError("Identity-sync token request failed")
		body = response.read(_MAX_TOKEN_RESPONSE_BYTES + 1)
	if len(body) > _MAX_TOKEN_RESPONSE_BYTES:
		raise ValueError("Identity-sync token response is too large")
	payload = json.loads(body)
	token = payload.get("access_token") if isinstance(payload, dict) else None
	if not isinstance(token, str) or not _BEARER.fullmatch(token):
		raise ValueError("Invalid identity-sync service token")
	expires_in = payload.get("expires_in")
	if type(expires_in) is int and expires_in > 5:
		_cached_bearer = (cache_key, token, now + min(expires_in, 86400) - 5)
	return token


def send_session_revocations(sessions):
	"""Send each pair and return only pairs that still need a delivery attempt."""
	sessions = tuple(dict.fromkeys(sessions))
	if not sessions:
		return ()

	try:
		endpoint = _configured_url("mobile_identity_sync_url", origin_only=True) + "/v1/sessions/revoke"
		bearer = _service_bearer()
	except _DELIVERY_ERRORS:
		failed = sessions
	else:
		failed = []
		for sid, subject in sessions:
			req = Request(
				endpoint,
				data=json.dumps({"sid": sid, "subject": subject}).encode("utf-8"),
				headers={"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"},
				method="POST",
			)
			try:
				with _OPENER.open(req, timeout=_TIMEOUT_SECONDS) as response:
					status = response.status
			except HTTPError as error:
				with error:
					status = error.code
			except _DELIVERY_ERRORS:
				status = None

			if status == 403:
				frappe.logger("mobile_sessions").error(
					"Identity-sync refused mobile session closure (HTTP 403). Local revocation remains in effect."
				)
			elif status != 200:
				failed.append((sid, subject))

	if failed:
		frappe.logger("mobile_sessions").warning(
			"One or more mobile session revocations could not be delivered."
		)
	return tuple(failed)
