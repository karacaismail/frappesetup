"""Sign-out: closes the Frappe session, builds the Keycloak logout address, handles back-channel logout (G-58)."""

import json
import time

import frappe
from frappe import _
from frappe.sessions import delete_session
from frappe.utils import get_datetime, now_datetime

from platform_core.kimlik import helpers, jwks, sign_in, site_settings
from platform_core.kimlik.exceptions import InvalidLogoutToken, KeycloakKeysUnavailable

LEEWAY = 30
BATCH = 100
MAX_BATCHES = 50
LOGOUT_REASON = "Logged out by identity provider"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
JTI_PREFIX = "kimlik_logout_jti"


def logout_current_session() -> dict:
	"""Closes the Frappe session and returns the Keycloak logout address.

	There is no `id_token_hint`: the ID token is not kept after sign-in.
	"""
	settings = site_settings.get()
	keycloak_sid = frappe.session.data.get("keycloak_sid")
	if helpers.is_session_id(keycloak_sid):
		sign_in.forget_keycloak_session(keycloak_sid, frappe.session.sid)
	frappe.local.login_manager.logout()
	return {
		"logout_url": helpers.end_session_url(
			settings.public_url, settings.realm, settings.client_id, settings.panel_url
		)
	}


def handle_logout_token(logout_token: object) -> dict:
	"""Verifies the logout token and closes the matching Frappe sessions."""
	frappe.local.response_headers["Cache-Control"] = "no-store"
	sign_in.guard_guest_request()
	if frappe.session.user != "Guest":
		_reject(_("Back-channel logout must not carry a session cookie.", context="platform_core.kimlik"))
	if not isinstance(logout_token, str) or not logout_token:
		_reject(_("Logout token is missing.", context="platform_core.kimlik"))
	if len(logout_token) > helpers.MAX_TOKEN_LENGTH:
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format("malformed"))

	from oidc_verify import TokenError, verify_logout_token

	settings = site_settings.get()
	try:
		claims = verify_logout_token(
			logout_token,
			cache=jwks.jwks_cache(settings.jwks_url),
			issuer=settings.issuer,
			client_id=settings.client_id,
			leeway=LEEWAY,
		)
	except TokenError as error:
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format(error.code))
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		jwks.report_keys_unavailable(settings.jwks_url)
		frappe.throw(
			_("Identity provider keys are not available.", context="platform_core.kimlik"),
			KeycloakKeysUnavailable,
		)

	_validate_logout_claims(claims)
	_mark_used_or_reject(claims)

	closed = 0
	sid = claims.get("sid")
	if helpers.is_session_id(sid):
		for frappe_sid in sign_in.frappe_sids_for(sid):
			if _session_exists(frappe_sid):
				delete_session(frappe_sid, reason=LOGOUT_REASON)
				closed += 1
		sign_in.forget_keycloak_session(sid)

	subject = claims.get("sub")
	if closed == 0 and isinstance(subject, str) and subject:
		user = frappe.db.get_value(
			"Platform Identity Link", {"issuer": settings.issuer, "subject": subject}, "user"
		)
		if user:
			closed += _close(sessions_for_user_before, user, int(claims["iat"]))

	return {"closed_sessions": closed}


def _validate_logout_claims(claims: dict) -> None:
	"""OpenID Connect Back-Channel Logout 1.0, section 2.4: exp and jti are required, the event value
	is a JSON object and sid, when present, is a string. The shared library does not enforce these yet.
	BORC(mvp): owner kimlik-realm. Closes when `oidc_verify` enforces these claims for logout tokens."""
	if not isinstance(claims.get("exp"), int | float) or isinstance(claims.get("exp"), bool):
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format("missing_exp"))
	jti = claims.get("jti")
	if not isinstance(jti, str) or not jti.strip():
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format("missing_jti"))
	events = claims.get("events")
	if not isinstance(events, dict) or not isinstance(events.get(LOGOUT_EVENT), dict):
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format("not_logout_token"))
	if "sid" in claims and not isinstance(claims["sid"], str):
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format("malformed"))


def _mark_used_or_reject(claims: dict) -> None:
	"""Replay protection: a `jti` is accepted once until the token expires (plus leeway)."""
	ttl = max(int(claims["exp"] - time.time()) + LEEWAY, 1)
	key = frappe.cache.make_key(f"{JTI_PREFIX}:{helpers.sha256_hex(claims['jti'])}")
	if not frappe.cache.set(key, "1", ex=ttl, nx=True):
		_reject(_("Logout token rejected: {0}", context="platform_core.kimlik").format("replayed"))


def _close(finder, *args) -> int:
	closed = 0
	for _round in range(MAX_BATCHES):
		rows = finder(*args)
		if not rows:
			break
		for sid, user in rows:
			delete_session(sid, user=user, reason=LOGOUT_REASON)
			closed += 1
		if len(rows) < BATCH:
			break
	return closed


def _session_exists(frappe_sid: str) -> bool:
	sessions = frappe.qb.DocType("Sessions")
	return bool(frappe.qb.from_(sessions).select(sessions.sid).where(sessions.sid == frappe_sid).run())


def sessions_for_user_before(user: str, iat: int) -> list[tuple[str, str]]:
	"""Sessions of the user that were created before the logout token was issued. A replayed or
	delayed token therefore never closes a session that was opened after it."""
	sessions = frappe.qb.DocType("Sessions")
	rows = (
		frappe.qb.from_(sessions)
		.select(sessions.sid, sessions.user, sessions.sessiondata)
		.where(sessions.user == user)
		.orderby(sessions.lastupdate)
		.orderby(sessions.sid)
		.limit(BATCH)
		.run()
	)
	now = now_datetime()
	selected = []
	for sid, owner, raw in rows:
		created = _created_epoch(raw, now)
		# `iat` has second precision; a session opened within that same second is treated as older.
		if created is None or created < iat + 1:
			selected.append((sid, owner))
	return selected


def _created_epoch(raw: str | None, now) -> float | None:
	"""Session creation time as a UNIX timestamp, derived from the age of the session record."""
	try:
		creation = json.loads(raw or "{}").get("creation")
	except ValueError:
		return None
	if not creation:
		return None
	age = (now - get_datetime(creation)).total_seconds()
	return time.time() - age


def _reject(message: str) -> None:
	frappe.throw(message, InvalidLogoutToken)
