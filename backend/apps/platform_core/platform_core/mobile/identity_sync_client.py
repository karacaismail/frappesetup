"""Deliver committed mobile session revocations to identity-sync."""

import json
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import frappe

from platform_core.identity.service_client import identity_sync_bearer, invalidate_identity_sync_bearer

_TIMEOUT_SECONDS = 3
_DELIVERY_ERRORS = (HTTPException, OSError, ValueError, RecursionError)


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		# The request carries credentials for the configured host only.
		return None


_OPENER = build_opener(_NoRedirect())


def _identity_sync_origin():
	value = frappe.conf.get("mobile_identity_sync_url")
	if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
		raise ValueError("Invalid identity-sync URL")
	address = urlsplit(value)
	if (
		address.scheme != "https"
		or not address.hostname
		or address.username is not None
		or address.query
		or address.fragment
		or address.path not in ("", "/")
	):
		raise ValueError("Invalid identity-sync URL")
	return value.rstrip("/")


def send_session_revocations(sessions):
	"""Send each pair and return only pairs that still need a delivery attempt."""
	sessions = tuple(dict.fromkeys(sessions))
	if not sessions:
		return ()

	try:
		endpoint = _identity_sync_origin() + "/v1/sessions/revoke"
		bearer = identity_sync_bearer()
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
				if status == 401:
					invalidate_identity_sync_bearer(bearer)
				failed.append((sid, subject))

	if failed:
		frappe.logger("mobile_sessions").warning(
			"One or more mobile session revocations could not be delivered."
		)
	return tuple(failed)
