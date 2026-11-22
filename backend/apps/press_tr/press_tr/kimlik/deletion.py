"""Authorize deletion requests using a freshly verified Press browser session."""

import time

import frappe
import requests
from frappe import _
from werkzeug.exceptions import BadGateway, ServiceUnavailable

from press_tr.kimlik.identity import IDENTITY_LINK, validate_local_user
from press_tr.kimlik.oidc import issuer, reject, server_endpoint, verify

ACCOUNT_DELETION_PAGE = "/account-deletion"
REAUTHENTICATION_TTL = 300


def human_identity():
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
		IDENTITY_LINK, {"user": frappe.session.user}, ["issuer", "subject"], as_dict=True
	)
	if not link or link.issuer != issuer():
		reject()
	return link


def fresh_reauthentication() -> int | None:
	authenticated_at = frappe.session.data.get("press_deletion_reauthenticated_at")
	if type(authenticated_at) is int and 0 <= int(time.time()) - authenticated_at <= REAUTHENTICATION_TTL:
		return authenticated_at
	return None


def record_reauthentication(attempt: dict, claims: dict) -> None:
	link = human_identity()
	auth_time = claims.get("auth_time")
	now = int(time.time())
	if (
		attempt["sid"] != frappe.session.sid
		or attempt["subject"] != link.subject
		or claims.get("iss") != link.issuer
		or claims.get("sub") != link.subject
		or type(auth_time) is not int
		or not max(attempt["started_at"], now - REAUTHENTICATION_TTL) <= auth_time <= now
	):
		reject()
	frappe.session.data.press_deletion_reauthenticated_at = auth_time
	frappe.local.session_obj.update(force=True)


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
	except requests.RequestException, ValueError, AttributeError:
		raise BadGateway() from None
	if response.status_code not in {200, 201, 202}:
		raise BadGateway()
