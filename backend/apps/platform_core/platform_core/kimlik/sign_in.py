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

import frappe
import frappe.sessions
from frappe import _
from frappe.utils import get_url

from platform_core.kimlik import helpers, jwks, site_settings
from platform_core.kimlik.exceptions import InvalidRedirect, KeycloakLoginNotConfigured, KeycloakSettingsMissing

LINK_DOCTYPE = "Platform Identity Link"
STATE_PREFIX = "kimlik_login_state"
STATE_TTL = 600
COOKIE_NAME = "kimlik_login"
SECURE_COOKIE_NAME = "__Host-kimlik_login"
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


def build_login_url(redirect_to: str | None = None) -> dict:
	"""Builds the Keycloak authorize address and binds the attempt to this browser."""
	if redirect_to and not helpers.is_safe_redirect(redirect_to):
		frappe.throw(_("Redirect target must be a relative path on this site."), InvalidRedirect)
	try:
		settings = site_settings.get()
	except KeycloakSettingsMissing:
		frappe.throw(_("Sign in with the identity provider is not configured."), KeycloakLoginNotConfigured)

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
		),
		"brand_name": settings.brand_name,
		"label": _("Sign in with {0}").format(settings.brand_name),
	}


def complete_callback(code: str | None, state: str | None, error: str | None = None) -> str:
	"""Finishes the sign-in. Returns the redirect target. Raises `SignInRefused` on any refusal."""
	if error:
		raise SignInRefused(400, _("The identity provider refused or cancelled the sign-in."))
	if not isinstance(state, str) or not state or not isinstance(code, str) or not code:
		raise SignInRefused(400, _("The sign-in response is incomplete."))

	record = _pop_state(state)
	if record is None:
		raise SignInRefused(400, _("This sign-in attempt is unknown, expired or already used. Please try again."))
	browser_token = frappe.request.cookies.get(_cookie_name()) if frappe.request else None
	if not browser_token:
		raise SignInRefused(400, _("The sign-in cookie is missing. Please start again in this browser."))
	if not hmac.compare_digest(helpers.sha256_hex(browser_token), record.get("browser", "")):
		raise SignInRefused(403, _("This sign-in was started in a different browser."))

	try:
		settings = site_settings.get()
	except KeycloakSettingsMissing as error:
		raise SignInRefused(503, _("Sign in with the identity provider is not configured.")) from error

	try:
		tokens = exchange_code(settings, code, record["verifier"], callback_url())
	except ExchangeFailed as error:
		raise SignInRefused(503, _("The identity provider could not be reached.")) from error
	id_token = tokens.get("id_token") if isinstance(tokens, dict) else None
	if not isinstance(id_token, str) or not id_token:
		raise SignInRefused(400, _("The identity provider did not return an identity token."))

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
		raise SignInRefused(400, _("The identity token is not valid ({0}).").format(error.code)) from error
	except Exception as error:
		if not jwks.is_keys_unavailable(error):
			raise
		raise SignInRefused(503, _("The identity provider keys are not available.")) from error

	user = resolve_user(settings.issuer, claims)
	frappe.local.login_manager.login_as(user)
	frappe.local.session.data.update(helpers.session_claims(claims, settings.issuer))
	# Frappe skips the CSRF check while the session has no token (frappe/auth.py:92). Create it now,
	# so the first write after sign-in already needs the X-Frappe-CSRF-Token header.
	frappe.sessions.get_csrf_token()
	frappe.local.session_obj.update(force=True)
	frappe.db.commit()
	frappe.local.cookie_manager.delete_cookie(_cookie_name())
	return record.get("redirect_to") or settings.panel_url


def resolve_user(issuer: str, claims: dict) -> str:
	"""Finds the Frappe user for `(iss, sub)`. Creates the first link only with a verified e-mail."""
	subject = claims.get("sub")
	if not isinstance(subject, str) or not subject.strip():
		raise SignInRefused(400, _("The identity provider did not send a subject."))
	subject = subject.strip()
	email = (claims.get("email") or "").strip().lower() if isinstance(claims.get("email"), str) else ""

	user = frappe.db.get_value(LINK_DOCTYPE, {"issuer": issuer, "subject": subject}, "user")
	if not user:
		if not email or not frappe.db.exists("User", email):
			raise SignInRefused(403, _("There is no account for this e-mail address. Sign-up is closed."))
		if frappe.db.exists(LINK_DOCTYPE, {"issuer": issuer, "user": email}):
			raise SignInRefused(403, _("This user is already linked to a different identity."))
		if not helpers.email_verified(claims):
			raise SignInRefused(403, _("The e-mail address is not verified by the identity provider."))
		if not frappe.db.get_value("User", email, "enabled"):
			raise SignInRefused(403, _("This user is disabled."))
		create_link(issuer, subject, email)
		return email

	if not frappe.db.get_value("User", user, "enabled"):
		raise SignInRefused(403, _("This user is disabled."))
	return user


def create_link(issuer: str, subject: str, user: str) -> str:
	"""Creates the identity link and returns its name.

	G-4: `ignore_permissions` is justified because the request runs as Guest and the target user comes from
	the identity provider's verified token, not from client input. The flag stays on the local document only.
	"""
	doc = frappe.new_doc(LINK_DOCTYPE)
	doc.update({"issuer": issuer, "subject": subject, "user": user})
	doc.insert(ignore_permissions=True)
	return doc.name


def exchange_code(settings, code: str, code_verifier: str, redirect_uri: str) -> dict:
	"""Exchanges the authorization code at the token endpoint. Only the configured Keycloak is called (G-13)."""
	import requests

	try:
		response = requests.post(
			helpers.token_url(settings.internal_url, settings.realm),
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
