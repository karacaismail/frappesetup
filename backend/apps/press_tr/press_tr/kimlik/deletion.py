"""Authorize deletion requests using a freshly verified Press browser session."""

import time

import frappe
import requests
from frappe import _
from werkzeug.exceptions import BadGateway, ServiceUnavailable

from press_tr.kimlik.identity import IDENTITY_LINK, remember_press_session, validate_local_user
from press_tr.kimlik.oidc import claim, issuer, reject, server_endpoint, verify

ACCOUNT_DELETION_PAGE = "/account-deletion"
REAUTHENTICATION_TTL = 300
REAUTHENTICATION_CLOCK_SKEW = 5


def human_identity(*, for_update=False):
	session = frappe.local.session_obj
	if (
		not session
		or frappe.session.user == "Guest"
		or frappe.request.cookies.get("sid") != session.sid
		or frappe.get_request_header("Authorization")
		or frappe.session.data.get("impersonated_by")
	):
		reject()
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


def send_deletion_request(link, authenticated_at: int) -> None:
	from oidc_verify import verify_access_token

	service_url = frappe.conf.identity_sync_url
	service_secret = frappe.conf.press_service_client_secret
	if not service_url or not service_secret:
		raise ServiceUnavailable(_("Configure the account deletion service.", context="press_tr"))

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
		response = requests.post(
			f"{service_url.rstrip('/')}/v1/account-deletions",
			headers={"Authorization": f"Bearer {token}"},
			json={"issuer": link.issuer, "subject": link.subject, "reauthenticated_at": authenticated_at},
			timeout=10,
			allow_redirects=False,
		)
	except (requests.RequestException, ValueError, AttributeError):
		raise BadGateway() from None
	if response.status_code not in {200, 201, 202}:
		raise BadGateway()
