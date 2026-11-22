"""Deliver committed mobile session revocations to identity-sync."""

import json
from http.client import HTTPException
from ipaddress import IPv6Address, ip_address
from urllib.error import HTTPError
from urllib.parse import SplitResult, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import frappe

from platform_core.identity.service_client import identity_sync_bearer, invalidate_identity_sync_bearer

_TIMEOUT_SECONDS = 3
_DELIVERY_ERRORS = (HTTPException, OSError, ValueError, RecursionError)


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		# The request carries credentials for the configured host only.
		return None


_OPENER = build_opener(_NoRedirect())
_LOCAL_OPENER = build_opener(ProxyHandler({}), _NoRedirect())


def _development_http_allowed(address: SplitResult) -> bool:
	if (
		address.scheme != "http"
		or frappe.conf.get("developer_mode") not in (1, "1")
		or frappe.conf.get("mobile_allow_development_http") not in (1, "1")
		or not address.hostname
		or address.port == 0
	):
		return False
	if address.hostname in ("localhost", "identity-sync.localhost"):
		return True
	try:
		host = ip_address(address.hostname)
		return host.is_loopback and not (isinstance(host, IPv6Address) and host.ipv4_mapped is not None)
	except ValueError:
		return False


def _identity_sync_origin():
	value = frappe.conf.get("mobile_identity_sync_url")
	if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
		raise ValueError("Invalid identity-sync URL")
	address = urlsplit(value)
	if (
		(address.scheme != "https" and not _development_http_allowed(address))
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
		opener = _LOCAL_OPENER if urlsplit(endpoint).scheme == "http" else _OPENER
		failed = []
		refreshed = False
		for index, (sid, subject) in enumerate(sessions):
			req = Request(
				endpoint,
				data=json.dumps({"sid": sid, "subject": subject}).encode("utf-8"),
				headers={"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"},
				method="POST",
			)
			try:
				with opener.open(req, timeout=_TIMEOUT_SECONDS) as response:
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
				if status == 401:
					invalidate_identity_sync_bearer(bearer)
					if not refreshed and index + 1 < len(sessions):
						try:
							bearer = identity_sync_bearer()
						except _DELIVERY_ERRORS:
							failed.extend(sessions[index + 1 :])
							break
						refreshed = True

	if failed:
		frappe.logger("mobile_sessions").warning(
			"One or more mobile session revocations could not be delivered."
		)
	return tuple(failed)
