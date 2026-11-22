import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

import frappe
import requests
from frappe.rate_limiter import rate_limit

from press_tr.kimlik.identity import bind_identity, ensure_personal_team
from press_tr.kimlik.oidc import callback_url, claim, issuer, reject, server_endpoint, verify

STATE_TTL = 300
STATE_COOKIE = "press_tr_login"


def state_key(state):
	return frappe.cache.make_key(f"press_tr:login:{state}")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def get_login_url() -> dict[str, str]:
	state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
	challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
	redirect_uri = callback_url()
	authorization_url = f"{issuer()}/protocol/openid-connect/auth"

	frappe.cache.setex(state_key(state), STATE_TTL, json.dumps({"nonce": nonce, "verifier": verifier}))
	frappe.local.cookie_manager.set_cookie(
		STATE_COOKIE, state, secure=redirect_uri.startswith("https:"), httponly=True, max_age=STATE_TTL
	)
	query = urlencode(
		{
			"client_id": "press",
			"redirect_uri": redirect_uri,
			"response_type": "code",
			"scope": "openid email profile",
			"state": state,
			"nonce": nonce,
			"code_challenge": challenge,
			"code_challenge_method": "S256",
		}
	)
	return {"url": f"{authorization_url}?{query}"}


def consume_login(state):
	cookie = frappe.request.cookies.get(STATE_COOKIE, "")
	if (
		not isinstance(state, str)
		or not state.isascii()
		or not cookie.isascii()
		or not secrets.compare_digest(state, cookie)
	):
		reject()
	data = frappe.cache.getdel(state_key(state))
	if not data:
		reject()
	frappe.local.cookie_manager.delete_cookie(STATE_COOKIE)
	return json.loads(data)


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
			auth=("press", frappe.conf.keycloak_client_secret),
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


@frappe.whitelist(allow_guest=True, methods=["GET"])
def keycloak_callback(state: str | None = None, code: str | None = None) -> None:
	# Frappe includes form fields in exception logs.
	frappe.form_dict.pop("state", None)
	frappe.form_dict.pop("code", None)
	login = consume_login(state)
	if not isinstance(code, str) or not code:
		reject()

	from oidc_verify import verify_id_token

	token = exchange_code(code, login["verifier"])
	claims = verify(verify_id_token, token, client_id="press", nonce=login["nonce"])
	keycloak_sid = claim(claims, "sid")
	try:
		link = bind_identity(claims)
		ensure_personal_team(link.user)
	except frappe.DuplicateEntryError, frappe.UniqueValidationError:
		reject()

	try:
		frappe.local.login_manager.login_as(link.user)
		frappe.get_doc(
			{
				"doctype": "Press Keycloak Session",
				"identity_link": link.name,
				"keycloak_sid": keycloak_sid,
				"press_sid": frappe.session.sid,
			}
		).insert(ignore_permissions=True)
	except Exception:
		if sid := getattr(getattr(frappe.local, "session_obj", None), "sid", None):
			frappe.cache.hdel("session", sid)
		frappe.local.cookie_manager.cookies.pop("sid", None)
		raise
	frappe.local.flags.commit = True
	frappe.local.response.update(type="redirect", location="/dashboard")
