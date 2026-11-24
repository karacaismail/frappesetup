"""AtonotA Login reads for the panel: sign-in platforms and linked accounts (AJA-459).

The site reads both lists from identity-sync. The site carries no Keycloak management role.

- The call uses the site's own service token (`service_client.identity_sync_bearer()`).
  The user's own sign-in token never leaves the site.
- The person comes only from the session: its `keycloak_sub` must match the identity link of
  `frappe.session.user` for the configured issuer. The request cannot name a person.
- The replies are built again here from an allow list. The panel contract is in `atonota-web`,
  `src/auth/README.md` (G-159 and G-160).
"""

import json
import re
from http.client import HTTPException
from ipaddress import IPv6Address, ip_address
from urllib.error import HTTPError
from urllib.parse import SplitResult, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import frappe
from frappe import _

from platform_core.identity import site_settings
from platform_core.identity.exceptions import (
	IdentityLinkMissing,
	IdentityServiceUnavailable,
	InvalidInput,
	LinkedAccountsForbidden,
)
from platform_core.identity.service_client import identity_sync_bearer, invalidate_identity_sync_bearer

# Requests per minute and signed-in user for each of the two methods.
RATE_LIMIT = 30
PROVIDERS_PATH = "/v1/login-providers"
LINKED_PATH = "/v1/linked-accounts"
IDENTITY_LINK = "PLT Identity Link"
_TIMEOUT_SECONDS = 3
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_SUBJECT_LENGTH = 128
# The panel accepts only this alias form and these sizes (G-159).
_ALIAS = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_MAX_DISPLAY_NAME = 80
_MAX_PROVIDERS = 100
# Frappe may put the command name into the request data. Nothing else is accepted.
_ALLOWED_PARAMETERS = frozenset({"cmd"})
_TRANSPORT_ERRORS = (HTTPException, OSError, ValueError, RecursionError)


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		# The request carries the service token for the configured host only.
		return None


_OPENER = build_opener(_NoRedirect())
_LOCAL_OPENER = build_opener(ProxyHandler({}), _NoRedirect())


def _flag(name: str) -> bool:
	return frappe.conf.get(name) in (1, "1")


def _development_http_allowed(address: SplitResult) -> bool:
	if (
		address.scheme != "http"
		or not _flag("developer_mode")
		or not _flag("mobile_allow_development_http")
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


def _identity_sync_origin() -> str:
	"""The identity-sync root. The phone session revocation uses the same setting."""
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


def _send(method: str, url: str, payload: dict | None, bearer: str) -> tuple[int, object]:
	"""One request to identity-sync. Returns the status and the decoded JSON body."""
	data = None if payload is None else json.dumps(payload).encode("utf-8")
	headers = {"Accept": "application/json", "Authorization": f"Bearer {bearer}"}
	if data is not None:
		headers["Content-Type"] = "application/json"
	req = Request(url, data=data, headers=headers, method=method)
	opener = _LOCAL_OPENER if urlsplit(url).scheme == "http" else _OPENER
	try:
		with opener.open(req, timeout=_TIMEOUT_SECONDS) as response:
			status = response.status
			body = response.read(_MAX_RESPONSE_BYTES + 1)
	except HTTPError as error:
		with error:
			return error.code, None
	if len(body) > _MAX_RESPONSE_BYTES:
		raise ValueError("identity-sync response is too large")
	return status, json.loads(body)


def _unavailable(endpoint: str, reason: str) -> IdentityServiceUnavailable:
	# The log names the endpoint and the reason. It never names the person, the address or the token.
	frappe.logger("login_reads").warning(
		"identity-sync read failed: endpoint=%s outcome=%s", endpoint, reason
	)
	return IdentityServiceUnavailable(
		_("The sign-in service is not available. Try again later.", context="platform_core.identity")
	)


def _call(endpoint: str, method: str, path: str, payload: dict | None) -> object:
	"""Call identity-sync once. A rejected token is dropped and the call is tried once more."""
	failure = None
	try:
		url = _identity_sync_origin() + path
		bearer = identity_sync_bearer()
	except _TRANSPORT_ERRORS:
		failure = "not_configured"
	if failure is not None:
		raise _unavailable(endpoint, failure)
	for attempt in range(2):
		try:
			status, body = _send(method, url, payload, bearer)
		except _TRANSPORT_ERRORS:
			failure = "no_answer"
			break
		if status == 200:
			return body
		if status == 403:
			frappe.logger("login_reads").info(
				"identity-sync read refused: endpoint=%s outcome=forbidden", endpoint
			)
			raise LinkedAccountsForbidden(
				_("You cannot read the sign-in accounts on this site.", context="platform_core.identity")
			)
		failure = f"status_{status}"
		if status != 401 or attempt:
			break
		invalidate_identity_sync_bearer(bearer)
		try:
			bearer = identity_sync_bearer()
		except _TRANSPORT_ERRORS:
			failure = "token_refused"
			break
	raise _unavailable(endpoint, failure or "no_answer")


def reject_parameters() -> None:
	"""The two methods take no parameters. A `subject` or `user` value never chooses the person."""
	if set(frappe.form_dict) - _ALLOWED_PARAMETERS:
		frappe.throw(_("This endpoint takes no parameters.", context="platform_core.identity"), InvalidInput)


def session_subject() -> str:
	"""The Keycloak subject of the current session, checked against the user's identity link.

	The subject comes from the session record that the sign-in wrote. It must belong to an
	identity link of `frappe.session.user` with the configured issuer. Otherwise no call is made.
	"""
	data = frappe.session.data or {}
	subject = data.get("keycloak_sub")
	configured = site_settings.issuer()
	if (
		not isinstance(subject, str)
		or not subject
		or len(subject) > _MAX_SUBJECT_LENGTH
		or data.get("keycloak_iss") != configured
		or not frappe.db.exists(
			IDENTITY_LINK, {"user": frappe.session.user, "issuer": configured, "subject": subject}
		)
	):
		raise IdentityLinkMissing(
			_("This session is not linked to an AtonotA Login account.", context="platform_core.identity")
		)
	return subject


def _provider_rows(value: object, endpoint: str, *, linked: bool) -> list[dict]:
	"""Rebuild the platform rows from an allow list. A broken row is dropped, a broken list is an error."""
	if not isinstance(value, list):
		raise _unavailable(endpoint, "invalid_reply")
	rows: list[dict] = []
	seen: set[str] = set()
	for row in value:
		if not isinstance(row, dict):
			continue
		alias, name = row.get("alias"), row.get("display_name")
		if not isinstance(alias, str) or not _ALIAS.fullmatch(alias) or alias in seen:
			continue
		if not isinstance(name, str) or not name.strip():
			continue
		item = {"alias": alias, "display_name": name.strip()[:_MAX_DISPLAY_NAME]}
		if linked:
			if not isinstance(row.get("linked"), bool):
				continue
			item["linked"] = row["linked"]
		seen.add(alias)
		rows.append(item)
	return rows[:_MAX_PROVIDERS]


def list_login_providers() -> dict:
	endpoint = "list_login_providers"
	reply = _call(endpoint, "GET", PROVIDERS_PATH, None)
	if not isinstance(reply, dict):
		raise _unavailable(endpoint, "invalid_reply")
	return {"providers": _provider_rows(reply.get("providers"), endpoint, linked=False)}


def list_linked_accounts() -> dict:
	endpoint = "list_linked_accounts"
	subject = session_subject()
	reply = _call(endpoint, "POST", LINKED_PATH, {"subject": subject})
	if not isinstance(reply, dict):
		raise _unavailable(endpoint, "invalid_reply")
	count = reply.get("local_sign_in_methods")
	if type(count) is not int or count < 0:
		raise _unavailable(endpoint, "invalid_reply")
	return {
		"providers": _provider_rows(reply.get("providers"), endpoint, linked=True),
		"local_sign_in_methods": count,
	}
