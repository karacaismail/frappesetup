"""Deliver committed mobile session revocations to identity-sync."""

import json
import re
from http.client import HTTPException
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
	url = _configured_url("mobile_identity_sync_token_url")
	client_id = frappe.conf.get("mobile_identity_sync_client_id")
	client_secret = frappe.conf.get("mobile_identity_sync_client_secret")
	if not all(isinstance(value, str) and value for value in (client_id, client_secret)):
		raise ValueError("Missing identity-sync service credentials")

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
	return token


def send_session_revocations(session_ids):
	"""Send once per distinct ID and return IDs that could not be delivered."""
	session_ids = tuple(dict.fromkeys(session_ids))
	if not session_ids:
		return ()

	try:
		endpoint = _configured_url("mobile_identity_sync_url", origin_only=True) + "/v1/sessions/revoke"
		bearer = _service_bearer()
	except _DELIVERY_ERRORS:
		failed = session_ids
	else:
		failed = []
		for sid in session_ids:
			req = Request(
				endpoint,
				data=json.dumps({"sid": sid}).encode("utf-8"),
				headers={"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"},
				method="POST",
			)
			try:
				with _OPENER.open(req, timeout=_TIMEOUT_SECONDS) as response:
					if response.status != 200:
						failed.append(sid)
			except _DELIVERY_ERRORS:
				failed.append(sid)

	if failed:
		frappe.logger("mobile_sessions").warning(
			"One or more mobile session revocations could not be delivered."
		)
	return tuple(failed)
