"""Sign-in through this app's own Keycloak callback (docs/sozlesmeler.md, section 5).

Frappe's built-in `login_via_keycloak` is not used: it does not bind `state` to the browser and it
drops the ID token, so the Keycloak session id is lost. This module

- starts the login: random browser token in an HttpOnly cookie, `state`, PKCE verifier and `nonce`
  stored server side for 600 seconds (`get_login_url`),
- finishes it: the state record is read and deleted in one atomic step (Redis GETDEL), the cookie
  hash must match, the code is exchanged with the PKCE verifier, the ID token is verified with
  `oidc_verify.verify_id_token` including `nonce`, the user is resolved by `(iss, sub)` (AU-4, G-120)
  and the Keycloak `sid` is written into the Frappe session record.
"""

import hmac
import json
import secrets
import time

import frappe
import frappe.sessions
from frappe import _
from frappe.utils import get_url

from platform_core.identity import helpers, jwks, session_policy, site_settings
from platform_core.identity.exceptions import (
	InvalidRedirect,
	KeycloakLoginNotConfigured,
	KeycloakSettingsMissing,
	PayloadTooLarge,
)

LINK_DOCTYPE = "PLT Identity Link"
STATE_PREFIX = "identity_login_state"
STATE_TTL = 600
COOKIE_NAME = "identity_login"
SECURE_COOKIE_NAME = "__Host-identity_login"
EXCHANGE_TIMEOUT = 10
LEEWAY = 30


class SignInRefused(Exception):
	"""Stops the browser flow with an HTTP status and a message safe to show."""

	def __init__(self, status: int, message: str):
		super().__init__(message)
		self.status = status
		self.message = message


class ExchangeFailed(Exception):
	"""The token endpoint did not return a token. The response body is never logged."""


def guard_guest_request(max_bytes: int = helpers.MAX_GUEST_BODY_BYTES) -> None:
	"""Guest endpoints refuse oversized bodies before doing any work (AU-14, review item O9)."""
	request = getattr(frappe.local, "request", None)
	length = getattr(request, "content_length", None) if request is not None else None
	if length and length > max_bytes:
		frappe.throw(_("Request body is too large.", context="platform_core.identity"), PayloadTooLarge)


def build_login_url(redirect_to: str | None = None, force_login: bool = False) -> dict:
	"""Builds the Keycloak authorize address and binds the attempt to this browser.

	`force_login` adds `prompt=login`: Keycloak asks for the credentials even with an open session (O-25).
	"""
	guard_guest_request()
	if redirect_to and not helpers.is_safe_redirect(redirect_to):
		frappe.throw(
			_("Redirect target must be a relative path on this site.", context="platform_core.identity"),
			InvalidRedirect,
		)
	try:
		settings = site_settings.get()
	except KeycloakSettingsMissing:
		frappe.throw(
			_("Sign in with the identity provider is not configured.", context="platform_core.identity"),
			KeycloakLoginNotConfigured,
		)

	browser_token = secrets.token_urlsafe(32)
	state = secrets.token_urlsafe(32)
	code_verifier = secrets.token_urlsafe(64)
	nonce = secrets.token_urlsafe(32)
	_save_state(
		state,
		{
			"browser": helpers.sha256_hex(browser_token),
			"verifier": code_verifier,
			"nonce": nonce,
			"redirect_to": redirect_to or "",
			"force_login": bool(force_login),
			"started_at": int(time.time()),
		},
	)
	frappe.local.cookie_manager.set_cookie(
		_cookie_name(), browser_token, max_age=STATE_TTL, httponly=True, samesite="Lax"
	)
	return {
		"login_url": helpers.authorize_url(
			settings.public_url,
			settings.realm,
			settings.client_id,
			callback_url(),
			state,
			nonce,
			helpers.code_challenge(code_verifier),
			prompt="login" if force_login else None,
		),
		"brand_name": settings.brand_name,
		"label": _("Sign in with {0}", context="platform_core.identity").format(settings.brand_name),
	}


def complete_callback(code: str | None, state: str | None, error: str | None = None) -> str:
	"""Finishes the sign-in. Returns the redirect target. Raises `SignInRefused` on any refusal."""
	guard_guest_request()
	if error:
		raise SignInRefused(
			400, _("The identity provider refused or cancelled the sign-in.", context="platform_core.identity")
		)
	if not isinstance(state, str) or not state or not isinstance(code, str) or not code:
		raise SignInRefused(400, _("The sign-in response is incomplete.", context="platform_core.identity"))
	if len(state) > helpers.MAX_STATE_LENGTH or len(code) > helpers.MAX_CODE_LENGTH:
		raise SignInRefused(400, _("The sign-in response is incomplete.", context="platform_core.identity"))

	record = _pop_state(state)
	if record is None:
		raise SignInRefused(
			400,
			_(
				"This sign-in attempt is unknown, expired or already used. Please try again.",
				context="platform_core.identity",
			),
		)
	browser_token = frappe.request.cookies.get(_cookie_name()) if frappe.request else None
	if not browser_token:
		raise SignInRefused(
			400,
			_(
				"The sign-in cookie is missing. Please start again in this browser.",
				context="platform_core.identity",
			),
		)
	if not hmac.compare_digest(helpers.sha256_hex(browser_token), record.get("browser", "")):
		raise SignInRefused(
			403, _("This sign-in was started in a different browser.", context="platform_core.identity")
		)

	try:
		settings = site_settings.get()
	except KeycloakSettingsMissing as error:
		raise SignInRefused(
			503, _("Sign in with the identity provider is not configured.", context="platform_core.identity")
		) from error

	try:
		tokens = exchange_code(settings, code, record["verifier"], callback_url())
	except ExchangeFailed as error:
		raise SignInRefused(
			503, _("The identity provider could not be reached.", context="platform_core.identity")
		) from error
	id_token = tokens.get("id_token") if isinstance(tokens, dict) else None
	if not isinstance(id_token, str) or not id_token:
		raise SignInRefused(
			400, _("The identity provider did not return an identity token.", context="platform_core.identity")
		)

	from oidc_verify import TokenError, verify_id_token

	try:
		claims = verify_id_token(
			id_token,
			cache=jwks.jwks_cache(settings.jwks_url),
			issuer=settings.issuer,
			client_id=settings.client_id,
			nonce=record["nonce"],
			leeway=LEEWAY,
		)
	except TokenError as error:
		raise SignInRefused(
			400,
			_("The identity token is not valid ({0}).", context="platform_core.identity").format(error.code),
		) from error
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		raise SignInRefused(
			503, _("The identity provider keys are not available.", context="platform_core.identity")
		) from error

	user = resolve_user(settings.issuer, claims)
	decision = session_policy.check_fresh_authentication(user, claims, record)
	if decision == "refuse":
		# O-25: the forced attempt must bring an authentication made during that attempt.
		raise SignInRefused(
			403,
			_("The identity provider did not confirm a fresh sign-in.", context="platform_core.identity"),
		)
	if decision == "force":
		# O-25: an employee idle for the limit authenticates again; the open Keycloak cookie does not count.
		return build_login_url(record.get("redirect_to") or None, force_login=True)["login_url"]
	_lock_identity_for_sign_in(settings.issuer, claims, user)
	frappe.local.login_manager.login_as(user)
	# Frappe commits right after it inserts the session row (frappe/sessions.py:301), which ends the lock.
	# Take it again and check once more: a deletion that ran in between has closed this session too.
	try:
		_lock_identity_for_sign_in(settings.issuer, claims, user)
	except Exception:
		# The failed recheck cannot roll back the session that login_as already committed.
		frappe.db.rollback()
		_close_new_session()
		raise
	frappe.local.session.data.update(helpers.session_claims(claims, settings.issuer))
	frappe.local.session.data["session_expiry"] = session_policy.IDLE_TIMEOUT
	remember_keycloak_session(claims.get("sid"), frappe.session.sid)
	# Frappe skips the CSRF check while the session has no token (frappe/auth.py:92). Create it now,
	# so the first write after sign-in already needs the X-Frappe-CSRF-Token header.
	frappe.sessions.get_csrf_token()
	frappe.local.session_obj.update(force=True)
	# V-2: the callback is a GET request, and Frappe does not commit GET requests on its own.
	frappe.db.commit()
	frappe.local.cookie_manager.delete_cookie(_cookie_name())
	return record.get("redirect_to") or settings.panel_url


def _lock_identity_for_sign_in(issuer: str, claims: dict, user: str) -> None:
	"""Merge review E1: sign-in and deletion take the same identity lock.

	The lock is held until the callback commits, so the session row exists before a deletion can run.
	A new transaction starts first: locking reads then see the latest committed rows. The account state
	is read again under the lock. Frappe's `login_as` does not check it (frappe/auth.py:357).
	"""
	from platform_core.identity import anonymization

	frappe.db.commit()
	link, record = anonymization.lock_identity(issuer, claims["sub"].strip(), require_key=False)
	refused = record or not link or link.user != user
	if not refused and not frappe.db.get_value("User", user, "enabled", for_update=True):
		refused = True
	if refused:
		raise SignInRefused(403, _("This user is disabled.", context="platform_core.identity"))


def _close_new_session() -> None:
	from frappe.sessions import delete_session

	sid = getattr(frappe.session, "sid", None)
	frappe.local.cookie_manager.delete_cookie("sid")
	if sid and sid != "Guest":
		delete_session(sid, reason="Sign-in identity recheck failed")


def resolve_user(issuer: str, claims: dict) -> str:
	"""Finds the Frappe user for `(iss, sub)`. Creates the first link only with a verified e-mail."""
	subject = claims.get("sub")
	if not isinstance(subject, str) or not subject.strip():
		raise SignInRefused(
			400, _("The identity provider did not send a subject.", context="platform_core.identity")
		)
	subject = subject.strip()
	email = (claims.get("email") or "").strip().lower() if isinstance(claims.get("email"), str) else ""
	from platform_core.identity import anonymization

	if anonymization.is_deleted(issuer, subject):
		raise SignInRefused(403, _("This user is disabled.", context="platform_core.identity"))

	user = frappe.db.get_value(LINK_DOCTYPE, {"issuer": issuer, "subject": subject}, "user")
	if not user:
		if not email or not frappe.db.exists("User", email):
			raise SignInRefused(
				403,
				_(
					"There is no account for this e-mail address. Sign-up is closed.",
					context="platform_core.identity",
				),
			)
		if frappe.db.exists(LINK_DOCTYPE, {"issuer": issuer, "user": email}):
			raise SignInRefused(
				403, _("This user is already linked to a different identity.", context="platform_core.identity")
			)
		if not helpers.email_verified(claims):
			raise SignInRefused(
				403,
				_(
					"The e-mail address is not verified by the identity provider.",
					context="platform_core.identity",
				),
			)
		if not frappe.db.get_value("User", email, "enabled"):
			raise SignInRefused(403, _("This user is disabled.", context="platform_core.identity"))
		create_link(issuer, subject, email)
		return email

	if email and email != user.lower():
		# The identity is linked, but the provider now reports another user's address (AU-4: refuse on mismatch).
		raise SignInRefused(
			403, _("This identity is linked to a different user.", context="platform_core.identity")
		)
	if not frappe.db.get_value("User", user, "enabled"):
		raise SignInRefused(403, _("This user is disabled.", context="platform_core.identity"))
	return user


def create_link(issuer: str, subject: str, user: str) -> str:
	"""Creates the identity link and returns its name.

	G-4: `ignore_permissions` is justified because the request runs as Guest and the target user comes from
	the identity provider's verified token, not from client input. The flag stays on the local document only.
	"""
	doc = frappe.new_doc(LINK_DOCTYPE)
	doc.update({"issuer": issuer, "subject": subject, "user": user})
	from frappe.database.database import savepoint

	inserted = False
	with savepoint(catch=(frappe.UniqueValidationError, frappe.DuplicateEntryError)):
		doc.insert(ignore_permissions=True)  # nosemgrep: frappe-ignore-permissions
		inserted = True
	if inserted:
		return doc.name
	# V-8: never accept an unseen winner. MariaDB can reject a locking read from this older snapshot.
	existing = frappe.db.get_value(
		LINK_DOCTYPE, {"issuer": issuer, "subject": subject}, ["name", "user"], as_dict=True
	)
	if existing and existing.user == user:
		return existing.name
	if not existing:
		raise SignInRefused(403, _("The identity link changed. Try again.", context="platform_core.identity"))
	raise SignInRefused(
		403, _("This identity is linked to a different user.", context="platform_core.identity")
	)


def exchange_code(settings, code: str, code_verifier: str, redirect_uri: str) -> dict:
	"""Exchanges the authorization code at the token endpoint. Only the configured Keycloak is called (G-13)."""
	import requests

	token_endpoint = helpers.token_url(settings.internal_url, settings.realm)
	try:
		response = requests.post(
			token_endpoint,
			data={
				"grant_type": "authorization_code",
				"code": code,
				"redirect_uri": redirect_uri,
				"client_id": settings.client_id,
				"client_secret": settings.client_secret,
				"code_verifier": code_verifier,
			},
			headers={"Accept": "application/json"},
			timeout=EXCHANGE_TIMEOUT,
		)
	except requests.RequestException as error:
		raise ExchangeFailed("request failed") from error
	if response.status_code != 200:
		raise ExchangeFailed(f"status {response.status_code}")
	try:
		return response.json()
	except ValueError as error:
		raise ExchangeFailed("invalid json") from error


def callback_url() -> str:
	return get_url(helpers.CALLBACK_PATH)


SID_INDEX_PREFIX = "kimlik_kc_sid"


def _sid_index_name(keycloak_sid: str) -> str:
	"""Unprefixed name of the index set. RedisWrapper prefixes it itself in `sadd`, `smembers`, `srem`,
	`expire_key` and `delete_value` (frappe/utils/redis_wrapper.py:365). One spelling for every call (T-4).
	"""
	return f"{SID_INDEX_PREFIX}:{helpers.sha256_hex(keycloak_sid)}"


def remember_keycloak_session(keycloak_sid: object, frappe_sid: str) -> None:
	"""Indexed lookup for back-channel logout: Keycloak sid -> Frappe sids (review item K9).

	The index lives in Redis for the session lifetime. If it is lost, the logout falls back to the
	`sub` claim, which closes the user's sessions opened before the token (see sign_out.py).
	"""
	if not helpers.is_session_id(keycloak_sid) or not frappe_sid:
		return
	from frappe.sessions import get_expiry_in_seconds

	name = _sid_index_name(keycloak_sid)
	frappe.cache.sadd(name, frappe_sid)
	frappe.cache.expire_key(name, get_expiry_in_seconds())


def frappe_sids_for(keycloak_sid: str) -> list[str]:
	members = frappe.cache.smembers(_sid_index_name(keycloak_sid)) or set()
	return sorted(m.decode() if isinstance(m, bytes) else str(m) for m in members)


def forget_keycloak_session(keycloak_sid: str, frappe_sid: str | None = None) -> None:
	name = _sid_index_name(keycloak_sid)
	if frappe_sid:
		frappe.cache.srem(name, frappe_sid)
	else:
		frappe.cache.delete_value(name)


def _cookie_name() -> str:
	request = getattr(frappe.local, "request", None)
	return SECURE_COOKIE_NAME if request is not None and request.scheme == "https" else COOKIE_NAME


def _state_key(state: str) -> str:
	return frappe.cache.make_key(f"{STATE_PREFIX}:{helpers.sha256_hex(state)}")


def _save_state(state: str, record: dict) -> None:
	frappe.cache.set(_state_key(state), json.dumps(record), ex=STATE_TTL)


def _pop_state(state: str) -> dict | None:
	"""Reads and deletes the state record in one atomic Redis command (GETDEL)."""
	raw = frappe.cache.getdel(_state_key(state))
	if not raw:
		return None
	try:
		record = json.loads(raw)
	except ValueError:
		return None
	return record if isinstance(record, dict) else None
