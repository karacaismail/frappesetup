import base64
import hashlib
import json
import secrets
from functools import wraps
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
from werkzeug.exceptions import Conflict

from press_tr.kimlik.deletion import ACCOUNT_DELETION_PAGE, record_reauthentication
from press_tr.kimlik.identity import bind_identity, ensure_personal_team, remember_press_session
from press_tr.kimlik.oidc import callback_url, claim, client_id, issuer, reject, server_endpoint, verify

STATE_TTL = 600
STATE_COOKIE = "press_tr_login"


def state_cookie():
	return "__Host-press_tr_login" if callback_url().startswith("https:") else STATE_COOKIE


def state_key(state: str, browser_digest: str) -> bytes:
	# Only the initiating browser can address and consume this login record.
	return frappe.cache.make_key(f"press_tr:login:{state}:{browser_digest}")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def get_login_url() -> dict[str, str]:
	return start_login()


def start_login(reauthentication: dict | None = None) -> dict[str, str]:
	state, nonce, verifier, browser = (secrets.token_urlsafe(32) for _ in range(4))
	browser_digest = hashlib.sha256(browser.encode("ascii")).hexdigest()
	challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
	redirect_uri = callback_url()
	authorization_url = f"{issuer()}/protocol/openid-connect/auth"

	login = {
		"browser_digest": browser_digest,
		"nonce": nonce,
		"verifier": verifier,
		"return_path": "/dashboard",
	}
	if reauthentication:
		login["reauthentication"] = reauthentication
	frappe.cache.setex(state_key(state, browser_digest), STATE_TTL, json.dumps(login))
	frappe.local.cookie_manager.set_cookie(
		state_cookie(),
		browser,
		secure=redirect_uri.startswith("https:"),
		httponly=True,
		samesite="Lax",
		max_age=STATE_TTL,
	)
	parameters = {
		"client_id": client_id(),
		"redirect_uri": redirect_uri,
		"response_type": "code",
		"scope": "openid email profile",
		"state": state,
		"nonce": nonce,
		"code_challenge": challenge,
		"code_challenge_method": "S256",
	}
	if reauthentication:
		parameters.update(prompt="login", max_age=0)
	return {"url": f"{authorization_url}?{urlencode(parameters)}"}


def consume_login(state: str | None):
	browser = frappe.request.cookies.get(state_cookie(), "")
	if (
		not isinstance(state, str)
		or len(state) != 43
		or len(browser) != 43
		or not state.isascii()
		or not browser.isascii()
	):
		reject()
	browser_digest = hashlib.sha256(browser.encode("ascii")).hexdigest()
	data = frappe.cache.getdel(state_key(state, browser_digest))
	if not data:
		reject()
	login = json.loads(data)
	if not secrets.compare_digest(login["browser_digest"], browser_digest):
		reject()
	frappe.local.cookie_manager.set_cookie(
		state_cookie(),
		"",
		secure=callback_url().startswith("https:"),
		httponly=True,
		samesite="Lax",
		max_age=0,
	)
	return login


def exchange_code(code, verifier):
	try:
		response = requests.post(
			server_endpoint("token"),
			data={
				"grant_type": "authorization_code",
				"code": code,
				"redirect_uri": callback_url(),
				"code_verifier": verifier,
			},
			auth=(client_id(), frappe.conf.keycloak_client_secret),
			timeout=10,
			allow_redirects=False,
		)
		if response.status_code == 200:
			payload = response.json()
			token = payload.get("id_token") if isinstance(payload, dict) else None
			if isinstance(token, str) and token:
				return token
	except requests.RequestException, ValueError:
		pass
	reject()


def redact_login_callback_fields(callback):
	@wraps(callback)
	def redacted(*args, **kwargs):
		# Frappe includes form fields in exception logs, including rate-limit errors.
		frappe.form_dict.pop("state", None)
		frappe.form_dict.pop("code", None)
		return callback(*args, **kwargs)

	return redacted


@frappe.whitelist(allow_guest=True, methods=["GET"])
@redact_login_callback_fields
@rate_limit(limit=10, seconds=60)
def keycloak_callback(state: str | None = None, code: str | None = None) -> None:
	login = consume_login(state)
	if not isinstance(code, str) or not code:
		reject()

	from oidc_verify import verify_id_token

	token = exchange_code(code, login["verifier"])
	claims = verify(verify_id_token, token, client_id=client_id(), nonce=login["nonce"])
	if reauthentication := login.get("reauthentication"):
		record_reauthentication(reauthentication, claims)
		frappe.local.response.update(type="redirect", location=ACCOUNT_DELETION_PAGE)
		return
	keycloak_sid = claim(claims, "sid")
	try:
		link = bind_identity(claims)
		ensure_personal_team(link.user)
	except frappe.QueryDeadlockError, frappe.QueryTimeoutError:
		raise Conflict(_("Concurrent account update. Start sign-in again.", context="press_tr"))
	except frappe.DuplicateEntryError, frappe.UniqueValidationError:
		reject()

	try:
		frappe.local.login_manager.login_as(link.user)
		# The OIDC callback is the only writer of this internal session mapping.
		remember_press_session(link.name, keycloak_sid)
	except Exception:
		if sid := getattr(getattr(frappe.local, "session_obj", None), "sid", None):
			frappe.cache.hdel("session", sid)
		frappe.local.cookie_manager.cookies.pop("sid", None)
		raise
	frappe.local.flags.commit = True
	frappe.local.response.update(type="redirect", location=login["return_path"])
