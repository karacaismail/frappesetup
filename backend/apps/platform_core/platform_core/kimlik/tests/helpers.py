"""Shared helpers of the identity tests.

HTTP requests run in a separate thread like Frappe's own API tests (`frappe.tests.test_api.make_request`),
so the test's `frappe.local` context stays intact. A request opens its own database connection. Test data
is therefore committed and the test connection is refreshed with `refresh()`.

Keys are generated locally on every run. There is no real person and no real secret.
"""

import time
from unittest.mock import patch

import frappe
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from frappe.installer import update_site_config
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from jwt.algorithms import RSAAlgorithm

# Expected values come from docs/sozlesmeler.md sections 2 and 8 (D-1).
TEST_SETTINGS = {
	"keycloak_public_url": "http://kimlik.localhost:8660",
	"keycloak_internal_url": "",
	"keycloak_realm": "platform",
	"keycloak_client_id": "site-kiraci1",
	"keycloak_client_secret": "test-client-secret-fake",
	"kimlik_marka_adi": "Atonota",
	"platform_panel_url": "http://kiraci1.localhost:8661/panel",
	"kimlik_yalniz_keycloak": 0,
	"kimlik_servis_azp": ["identity-sync"],
}
ISSUER = "http://kimlik.localhost:8660/realms/platform"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
CALLBACK = "/api/method/platform_core.api.auth.keycloak_callback"
LOGIN_COOKIE = "kimlik_login"

AYSE = "ayse.ornek@example.test"
MEHMET = "mehmet.ornek@example.test"
UNVERIFIED = "dogrulanmamis@example.test"
SAMPLE_USERS = (AYSE, MEHMET, UNVERIFIED)


def refresh():
	"""Refreshes the test connection so rows committed by other connections become visible."""
	frappe.db.commit()


class SiteSettings:
	"""Writes test values into site config and restores the old values on exit."""

	def __init__(self, overrides: dict | None = None):
		self.values = {**TEST_SETTINGS, **(overrides or {})}
		self.old = {}

	def __enter__(self):
		for key, value in self.values.items():
			self.old[key] = frappe.conf.get(key)
			update_site_config(key, value, validate=False)
			frappe.local.conf[key] = value
		return self

	def __exit__(self, *_):
		for key, old in self.old.items():
			# update_site_config removes a key only for the literal "None" (frappe/installer.py:716).
			update_site_config(key, "None" if old is None else old, validate=False)
			if old is None:
				frappe.local.conf.pop(key, None)


def ensure_user(email: str, user_type: str = "Website User", roles: list | None = None) -> str:
	if frappe.db.exists("User", email):
		return email
	user = frappe.new_doc("User")
	user.update(
		{
			"email": email,
			"first_name": email.split("@")[0].split(".")[0].title(),
			"user_type": user_type,
			"enabled": 1,
			"send_welcome_email": 0,
		}
	)
	for role in roles or []:
		user.append("roles", {"role": role})
	user.insert(ignore_permissions=True)
	return user.name


def clear_sessions_of(*users: str) -> None:
	"""Closes every session of the given users so counts in later tests start from zero."""
	from frappe.sessions import delete_session

	sessions = frappe.qb.DocType("Sessions")
	for user in users:
		for sid in (
			frappe.qb.from_(sessions).select(sessions.sid).where(sessions.user == user).run(pluck=True)
		):
			delete_session(sid, user=user, reason="Test cleanup")


def reset_rate_limits() -> None:
	"""Rate limits count per IP; the test client always comes from the same address (frappe/rate_limiter.py)."""
	frappe.cache.delete_keys("rl:")


def clear_links(*extra_users: str):
	"""Removes identity links of the test issuer, closes sessions of the sample users, resets rate limits."""
	frappe.db.delete("Platform Identity Link", {"issuer": ISSUER})
	clear_sessions_of(*SAMPLE_USERS, *extra_users)
	reset_rate_limits()
	refresh()


def make_link(subject: str, user: str, issuer: str = ISSUER):
	doc = frappe.get_doc(
		{"doctype": "Platform Identity Link", "issuer": issuer, "subject": subject, "user": user}
	)
	doc.insert(ignore_permissions=True)
	refresh()
	return doc


def userinfo(sub: str, email: str, email_verified: bool = True, sid: str | None = None, **extra) -> dict:
	"""Fake claims shaped like a Keycloak userinfo response."""
	data = {
		"sub": sub,
		"email": email,
		"email_verified": email_verified,
		"preferred_username": email,
		"given_name": "Ornek",
		"family_name": "Kullanici",
	}
	if sid:
		data["sid"] = sid
	data.update(extra)
	return data


def request(method, *args, **kwargs):
	"""Runs a test-client request in a separate thread."""
	return make_request(target=method, args=args, kwargs=kwargs)


def new_client():
	return get_test_client()


KEY = None
"""Shared signing key for fake Keycloak tokens. Created lazily so that import stays cheap."""

exchange_calls: list[dict] = []
"""Arguments the fake code exchange received, for assertions on PKCE wiring."""


def key() -> "Key":
	global KEY
	if KEY is None:
		KEY = Key()
	return KEY


def start_login(client, redirect_to: str | None = None, headers: dict | None = None):
	"""Calls get_login_url and returns (response, parsed authorize query)."""
	from urllib.parse import parse_qs, urlparse

	body = {"redirect_to": redirect_to} if redirect_to else {}
	response = request(
		client.post, "/api/method/platform_core.api.auth.get_login_url", json=body, headers=headers or {}
	)
	query = {}
	if response.status_code == 200:
		query = {k: v[0] for k, v in parse_qs(urlparse(response.json["message"]["login_url"]).query).items()}
	return response, query


def id_token(query: dict, claims: dict, signing_key: "Key | None" = None, **overrides) -> str:
	"""Signs an ID token like Keycloak would for the authorize request described by `query`."""
	now = int(time.time())
	payload = {
		"iss": ISSUER,
		"aud": TEST_SETTINGS["keycloak_client_id"],
		"azp": TEST_SETTINGS["keycloak_client_id"],
		"iat": now,
		"exp": now + 300,
		"auth_time": now,
		"nonce": query.get("nonce"),
		"typ": "ID",
	}
	payload.update(claims)
	payload.update(overrides)
	return (signing_key or key()).sign({k: v for k, v in payload.items() if v is not None})


def fake_exchange(token: str | None = None, **token_response):
	"""Patch for `sign_in.exchange_code` that returns a Keycloak-like token response without network."""

	def exchange(settings, code, code_verifier, redirect_uri):
		exchange_calls.append(
			{
				"code": code,
				"code_verifier": code_verifier,
				"redirect_uri": redirect_uri,
				"client_id": settings.client_id,
			}
		)
		return {
			"id_token": token,
			"access_token": "fake-access-token",
			"token_type": "Bearer",
			**token_response,
		}

	return patch("platform_core.kimlik.sign_in.exchange_code", side_effect=exchange)


def finish_login(client, query: dict, token: str, code: str = "test-code", state: str | None = None):
	"""Calls the callback with the fake token exchange in place."""
	with fake_exchange(token):
		return request(
			client.get,
			CALLBACK,
			query_string={"code": code, "state": state if state is not None else query.get("state")},
		)


def login_with_keycloak(client, claims: dict, redirect_to: str | None = None):
	"""Full sign-in through this app's own callback. Only Keycloak itself is faked (token exchange)."""
	started, query = start_login(client, redirect_to)
	if started.status_code != 200:
		return started
	return finish_login(client, query, id_token(query, claims))


def logged_user(client) -> str:
	"""Current user of the client's session. `get_logged_user` is not open to guests, so 403 means Guest."""
	response = request(client.get, "/api/method/frappe.auth.get_logged_user")
	if response.status_code == 403 and response.json.get("exc_type") == "PermissionError":
		return "Guest"
	if response.status_code == 401 and response.json.get("exc_type") == "SessionExpired":
		# The cookie points at a deleted session (frappe/sessions.py:346).
		return "Guest"
	return response.json.get("message")


def csrf_token_of(client) -> str | None:
	"""CSRF token stored in the session the client's `sid` cookie points at."""
	refresh()
	cookie = client.get_cookie("sid")
	if not cookie:
		return None
	sessions = frappe.qb.DocType("Sessions")
	rows = frappe.qb.from_(sessions).select(sessions.sessiondata).where(sessions.sid == cookie.value).run()
	if not rows:
		return None
	return frappe.parse_json(rows[0][0] or "{}").get("csrf_token")


def csrf_headers(client) -> dict:
	token = csrf_token_of(client)
	return {"X-Frappe-CSRF-Token": token} if token else {}


def session_count(user: str) -> int:
	refresh()
	sessions = frappe.qb.DocType("Sessions")
	return len(frappe.qb.from_(sessions).select(sessions.sid).where(sessions.user == user).run(pluck=True))


def sessions_containing(fragment: str) -> list:
	refresh()
	sessions = frappe.qb.DocType("Sessions")
	return (
		frappe.qb.from_(sessions)
		.select(sessions.sid)
		.where(sessions.sessiondata.like(f"%{fragment}%"))
		.run(pluck=True)
	)


class Key:
	"""Locally generated RSA key. Signs tokens and produces a JWKS."""

	def __init__(self, kid: str = "test-kid"):
		self.kid = kid
		self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		self.private_pem = self.private.private_bytes(
			serialization.Encoding.PEM,
			serialization.PrivateFormat.PKCS8,
			serialization.NoEncryption(),
		)

	def jwk(self) -> dict:
		data = RSAAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
		data.update({"kid": self.kid, "alg": "RS256", "use": "sig"})
		return data

	def jwks(self) -> dict:
		return {"keys": [self.jwk()]}

	def sign(self, payload: dict, alg: str = "RS256", kid: str | None = None) -> str:
		headers = {"kid": kid or self.kid}
		if alg == "none":
			return jwt.encode(payload, key=None, algorithm="none", headers=headers)
		return jwt.encode(payload, self.private_pem, algorithm=alg, headers=headers)


def logout_payload(**overrides) -> dict:
	now = int(time.time())
	payload = {
		"iss": ISSUER,
		"aud": "site-kiraci1",
		"iat": now,
		"exp": now + 120,
		"jti": frappe.generate_hash(length=16),
		"events": {LOGOUT_EVENT: {}},
		"sub": "sub-ayse",
		"sid": "11111111-1111-4111-8111-111111111111",
	}
	payload.update(overrides)
	return {k: v for k, v in payload.items() if v is not None}


def access_payload(**overrides) -> dict:
	now = int(time.time())
	payload = {
		"iss": ISSUER,
		"sub": "service-account-identity-sync",
		"aud": "site-kiraci1",
		"azp": "identity-sync",
		"iat": now,
		"exp": now + 300,
		"typ": "Bearer",
	}
	payload.update(overrides)
	return {k: v for k, v in payload.items() if v is not None}


def jwks_patch(signing_key: "Key | None" = None):
	"""Patch that feeds `platform_core.kimlik.jwks.jwks_cache` with the local key."""
	from oidc_verify import JwksCache

	signing_key = signing_key or key()

	def fake(jwks_url: str):
		return JwksCache(jwks_url, ttl_seconds=600, fetcher=signing_key.jwks)

	return patch("platform_core.kimlik.jwks.jwks_cache", side_effect=fake)


def jwks_unavailable_patch():
	"""Simulates a Keycloak whose key list cannot be fetched."""
	from oidc_verify import JwksCache

	def failing():
		raise OSError("JWKS fetch failed")

	def fake(jwks_url: str):
		return JwksCache(jwks_url, ttl_seconds=600, fetcher=failing)

	return patch("platform_core.kimlik.jwks.jwks_cache", side_effect=fake)


def ensure_system_manager(email: str, password: str) -> str:
	"""A System User with a known password for password sign-in tests. Fictional address."""
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	user = frappe.new_doc("User")
	user.update(
		{
			"email": email,
			"first_name": "Kimlik",
			"user_type": "System User",
			"enabled": 1,
			"send_welcome_email": 0,
			"new_password": password,
		}
	)
	user.append("roles", {"role": "System Manager"})
	user.insert(ignore_permissions=True)
	return user.name


class single_value:
	"""Temporarily sets one field of a Single DocType without validating the whole document."""

	def __init__(self, doctype: str, field: str, value):
		self.doctype, self.field, self.value = doctype, field, value

	def __enter__(self):
		self.old = frappe.db.get_single_value(self.doctype, self.field)
		frappe.db.set_single_value(self.doctype, self.field, self.value)
		refresh()
		return self

	def __exit__(self, *_):
		frappe.db.set_single_value(self.doctype, self.field, self.old)
		refresh()


def ensure_role(name: str, desk_access: int) -> str:
	if frappe.db.exists("Role", name):
		return name
	doc = frappe.new_doc("Role")
	doc.update({"role_name": name, "desk_access": desk_access})
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_role_profile(name: str, roles: list[str]) -> str:
	if frappe.db.exists("Role Profile", name):
		return name
	doc = frappe.new_doc("Role Profile")
	doc.role_profile = name
	for role in roles:
		doc.append("roles", {"role": role})
	doc.insert(ignore_permissions=True)
	return doc.name
