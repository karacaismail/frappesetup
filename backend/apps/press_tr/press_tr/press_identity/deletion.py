"""Authorize deletion requests using a freshly verified Press browser session."""

import json
import logging
import time

import frappe
import requests
from frappe import _
from urllib3.exceptions import HTTPError, ReadTimeoutError
from werkzeug.exceptions import BadGateway, ServiceUnavailable

from press_tr.press_identity.identity import IDENTITY_LINK, remember_press_session, validate_local_user
from press_tr.press_identity.oidc import claim, issuer, reject, server_endpoint, verify

ACCOUNT_DELETION_PAGE = "/account-deletion"
REAUTHENTICATION_TTL = 300
REAUTHENTICATION_CLOCK_SKEW = 5
DEFAULT_DELETION_TIMEOUT = 45
MAX_DELETION_TIMEOUT = 90
DELETION_CONNECT_TIMEOUT = 10
MAX_DELETION_RESPONSE_BYTES = 8 * 1024 * 1024
KEY_REMOVAL_TIMEOUT = 30
MAX_KEY_REMOVAL_RESPONSE_BYTES = 65536
# Short codes for the review record. They never carry personal data (AJA-420).
KEY_REMOVAL_ERRORS = ("not_configured", "upstream_failed", "unknown")


class KeyRemovalFailed(Exception):
	"""The key removal did not finish. `code` is one of KEY_REMOVAL_ERRORS."""

	def __init__(self, code: str):
		if code not in KEY_REMOVAL_ERRORS:
			raise ValueError("unknown key removal error code")
		super().__init__(code)
		self.code = code


def browser_session() -> None:
	"""Allow only a person in a Press browser session: no token, no impersonation."""
	session = frappe.local.session_obj
	if (
		not session
		or frappe.session.user == "Guest"
		or frappe.request.cookies.get("sid") != session.sid
		or frappe.get_request_header("Authorization")
		or frappe.session.data.get("impersonated_by")
	):
		reject()


def human_identity(*, for_update=False):
	browser_session()
	validate_local_user(frappe.session.user)
	link = frappe.db.get_value(
		IDENTITY_LINK,
		{"user": frappe.session.user},
		["name", "issuer", "subject"],
		as_dict=True,
		for_update=for_update,
	)
	if not link or link.issuer != issuer():
		reject()
	return link


def reauthentication_key() -> str:
	return f"press_tr:deletion_reauthenticated_at:{frappe.session.sid}"


def fresh_reauthentication() -> int | None:
	authenticated_at = frappe.cache.get_value(reauthentication_key())
	if type(authenticated_at) is int and 0 <= int(time.time()) - authenticated_at <= REAUTHENTICATION_TTL:
		return authenticated_at
	return None


def clear_reauthentication() -> None:
	frappe.cache.delete_value(reauthentication_key())


def record_reauthentication(attempt: dict, claims: dict) -> None:
	link = human_identity(for_update=True)
	auth_time = claims.get("auth_time")
	now = int(time.time())
	earliest = max(attempt["started_at"] - REAUTHENTICATION_CLOCK_SKEW, now - REAUTHENTICATION_TTL)
	if (
		attempt["sid"] != frappe.session.sid
		or attempt["subject"] != link.subject
		or claims.get("iss") != link.issuer
		or claims.get("sub") != link.subject
		or type(auth_time) is not int
		or not earliest <= auth_time <= now
	):
		reject()
	remember_press_session(link.name, claim(claims, "sid"))
	# Keep the proof separate from Frappe session data so clearing it never restores a revoked session.
	key = reauthentication_key()
	frappe.db.after_commit.add(
		lambda: frappe.cache.set_value(key, auth_time, expires_in_sec=REAUTHENTICATION_TTL)
	)
	frappe.local.flags.commit = True


def deletion_status() -> str | None:
	for status in ("submitted", "pending"):
		if frappe.cache.get_value(f"press_tr:deletion:{status}:{frappe.session.sid}"):
			return status
	return None


def mark_deletion_status(status: str) -> None:
	frappe.cache.set_value(
		f"press_tr:deletion:{status}:{frappe.session.sid}", True, expires_in_sec=REAUTHENTICATION_TTL
	)


def service_token(service_secret: str) -> str:
	"""A Keycloak token of the Press service client for identity-sync. Press never gets an admin token."""
	from oidc_verify import verify_access_token

	try:
		response = requests.post(
			server_endpoint("token"),
			data={"grant_type": "client_credentials", "scope": "aud-identity-sync"},
			auth=("press-service", service_secret),
			timeout=10,
			allow_redirects=False,
		)
		if response.status_code != 200:
			raise BadGateway()
		token = response.json().get("access_token")
		if not isinstance(token, str) or not token:
			raise BadGateway()
		verify(verify_access_token, token, audience="identity-sync", allowed_azp={"press-service"})
	except (requests.RequestException, ValueError, AttributeError):
		raise BadGateway() from None
	return token


def send_key_removal_request(link, review_id: str, approved_at: int) -> int:
	"""Ask identity-sync to remove the old keys after an approved recovery (AJA-420).

	Returns how many keys the service removed. Every failure raises KeyRemovalFailed with a short code.
	"""
	service_url = frappe.conf.identity_sync_url
	service_secret = frappe.conf.press_service_client_secret
	if not service_url or not service_secret:
		raise KeyRemovalFailed("not_configured")
	try:
		token = service_token(service_secret)
	except (BadGateway, ServiceUnavailable, frappe.PermissionError):
		# Keycloak refused or could not check the service token. Only missing settings are not_configured.
		raise KeyRemovalFailed("upstream_failed") from None
	try:
		response = requests.post(
			f"{service_url.rstrip('/')}/v1/recovery-key-removals",
			headers={"Authorization": f"Bearer {token}"},
			json={"issuer": link.issuer, "subject": link.subject, "review_id": review_id, "approved_at": approved_at},
			timeout=(DELETION_CONNECT_TIMEOUT, KEY_REMOVAL_TIMEOUT),
			allow_redirects=False,
			stream=True,
		)
	except requests.ReadTimeout:
		# The service may still have removed the keys. A new call finds out.
		raise KeyRemovalFailed("unknown") from None
	except requests.RequestException:
		raise KeyRemovalFailed("upstream_failed") from None
	try:
		if response.status_code != 200:
			raise KeyRemovalFailed("upstream_failed")
		body = response.raw.read(MAX_KEY_REMOVAL_RESPONSE_BYTES + 1, decode_content=True)
		if len(body) > MAX_KEY_REMOVAL_RESPONSE_BYTES:
			raise KeyRemovalFailed("upstream_failed")
		result = json.loads(body)
		if not isinstance(result, dict) or result.get("status") != "done":
			raise KeyRemovalFailed("upstream_failed")
		removed = result.get("removed")
		if type(removed) is not int or removed < 0:
			raise KeyRemovalFailed("upstream_failed")
		return removed
	except (requests.ReadTimeout, ReadTimeoutError):
		raise KeyRemovalFailed("unknown") from None
	except (requests.RequestException, HTTPError, ValueError, AttributeError):
		raise KeyRemovalFailed("upstream_failed") from None
	finally:
		response.close()


def send_deletion_request(link, authenticated_at: int) -> bool:
	service_url = frappe.conf.identity_sync_url
	service_secret = frappe.conf.press_service_client_secret
	if not service_url or not service_secret:
		raise ServiceUnavailable(_("Configure the account deletion service.", context="press_tr"))

	timeout = frappe.conf.get("press_deletion_request_timeout", DEFAULT_DELETION_TIMEOUT)
	if type(timeout) not in (int, float) or not 0 < timeout <= MAX_DELETION_TIMEOUT:
		logging.getLogger("press_tr").warning(
			"press_deletion_request_timeout must be a positive number no greater than %s seconds.",
			MAX_DELETION_TIMEOUT,
		)
		raise ServiceUnavailable(_("Configure the account deletion service.", context="press_tr"))

	token = service_token(service_secret)

	try:
		response = requests.post(
			f"{service_url.rstrip('/')}/v1/account-deletions",
			headers={"Authorization": f"Bearer {token}"},
			json={"issuer": link.issuer, "subject": link.subject, "reauthenticated_at": authenticated_at},
			timeout=(DELETION_CONNECT_TIMEOUT, timeout),
			allow_redirects=False,
			stream=True,
		)
	except requests.ReadTimeout:
		return False
	except requests.RequestException:
		raise BadGateway() from None
	try:
		if response.status_code not in {200, 201, 202}:
			raise BadGateway()
		if response.status_code != 200:
			return True
		body = response.raw.read(MAX_DELETION_RESPONSE_BYTES + 1, decode_content=True)
		if len(body) > MAX_DELETION_RESPONSE_BYTES:
			raise BadGateway()
		result = json.loads(body)
		if not isinstance(result, dict) or not isinstance(result.get("status"), str):
			raise BadGateway()
		return result["status"] != "unknown"
	except (requests.ReadTimeout, ReadTimeoutError):
		return False
	except (requests.RequestException, HTTPError, ValueError):
		raise BadGateway() from None
	finally:
		response.close()
