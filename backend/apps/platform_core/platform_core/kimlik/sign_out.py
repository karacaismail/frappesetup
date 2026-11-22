"""Sign-out: closes the Frappe session, builds the Keycloak logout address, handles back-channel logout (G-58)."""

import frappe
from frappe import _
from frappe.sessions import delete_session
from oidc_verify import TokenError, verify_logout_token

from platform_core.kimlik import helpers, jwks, site_settings
from platform_core.kimlik.exceptions import InvalidLogoutToken, KeycloakKeysUnavailable

LEEWAY = 30
MAX_SESSIONS = 100
LOGOUT_REASON = "Logged out by identity provider"


def logout_current_session() -> dict:
	"""Closes the Frappe session and returns the Keycloak logout address.

	There is no `id_token_hint`: Frappe's built-in sign-in does not keep the ID token.
	"""
	settings = site_settings.get()
	frappe.local.login_manager.logout()
	frappe.db.commit()
	return {
		"logout_url": helpers.end_session_url(
			settings.public_url, settings.realm, settings.client_id, settings.panel_url
		)
	}


def handle_logout_token(logout_token: object) -> dict:
	"""Verifies the logout token and closes the matching Frappe sessions."""
	frappe.local.response_headers["Cache-Control"] = "no-store"
	if frappe.session.user != "Guest":
		frappe.throw(_("Back-channel logout must not carry a session cookie."), InvalidLogoutToken)
	if not isinstance(logout_token, str) or not logout_token:
		frappe.throw(_("Logout token is missing."), InvalidLogoutToken)

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
		frappe.throw(_("Logout token rejected: {0}").format(error.code), InvalidLogoutToken)
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		frappe.throw(_("Identity provider keys are not available."), KeycloakKeysUnavailable)

	closed = 0
	sid = claims.get("sid")
	if helpers.is_session_id(sid):
		for frappe_sid in sessions_for_keycloak_sid(sid):
			delete_session(frappe_sid, reason=LOGOUT_REASON)
			closed += 1

	subject = claims.get("sub")
	if closed == 0 and isinstance(subject, str) and subject:
		user = frappe.db.get_value(
			"Platform Identity Link", {"issuer": settings.issuer, "subject": subject}, "user"
		)
		if user:
			for frappe_sid in sessions_for_user(user):
				delete_session(frappe_sid, user=user, reason=LOGOUT_REASON)
				closed += 1

	return {"closed_sessions": closed}


def sessions_for_keycloak_sid(sid: str) -> list[str]:
	"""Frappe sessions whose data carries this Keycloak `sid`. The format is restricted by `is_session_id`."""
	sessions = frappe.qb.DocType("Sessions")
	return (
		frappe.qb.from_(sessions)
		.select(sessions.sid)
		.where(sessions.sessiondata.like(f"%{helpers.session_marker(sid)}%"))
		.limit(MAX_SESSIONS)
		.run(pluck=True)
	)


def sessions_for_user(user: str) -> list[str]:
	sessions = frappe.qb.DocType("Sessions")
	return (
		frappe.qb.from_(sessions)
		.select(sessions.sid)
		.where(sessions.user == user)
		.orderby(sessions.lastupdate)
		.limit(MAX_SESSIONS)
		.run(pluck=True)
	)
