"""Sign-in with Keycloak.

The callback is Frappe's own `frappe.integrations.oauth2_logins.login_via_keycloak`. Frappe finds the user
by e-mail. This module checks the permanent key `(iss, sub)` in the `on_social_login` hook (AU-4, G-120).
The hook runs at `frappe/utils/oauth.py:262`, before `login_as`. A `PermissionError` stops the sign-in.
"""

import frappe
from frappe import _
from frappe.utils.oauth import get_oauth2_authorize_url

from platform_core.kimlik import helpers, site_settings
from platform_core.kimlik.exceptions import InvalidRedirect, KeycloakLoginNotConfigured

SESSION_FLAG = "kimlik_session_claims"
LINK_DOCTYPE = "Platform Identity Link"


def build_login_url(redirect_to: str | None = None) -> dict:
	"""Builds the Keycloak authorize address. `state` is generated on the server (Frappe cache)."""
	if redirect_to and not helpers.is_safe_redirect(redirect_to):
		frappe.throw(_("Redirect target must be a relative path on this site."), InvalidRedirect)
	settings = site_settings.get()
	if not frappe.db.get_value("Social Login Key", helpers.PROVIDER, "enable_social_login"):
		frappe.throw(
			_("Sign in with {0} is not configured.").format(settings.brand_name), KeycloakLoginNotConfigured
		)
	return {
		"login_url": get_oauth2_authorize_url(helpers.PROVIDER, redirect_to or None),
		"brand_name": settings.brand_name,
		"label": _("Sign in with {0}").format(settings.brand_name),
	}


def on_social_login(user: str, provider: str, claims: dict) -> None:
	"""Checks the user by `(iss, sub)`. Creates the first link only with a verified e-mail."""
	if provider != helpers.PROVIDER:
		return
	issuer = site_settings.issuer()
	subject = claims.get("sub")
	if not isinstance(subject, str) or not subject.strip():
		_refuse(_("The identity provider did not send a subject."))
	subject = subject.strip()

	link = frappe.db.get_value(
		LINK_DOCTYPE, {"issuer": issuer, "subject": subject}, ["name", "user"], as_dict=True
	)
	if link:
		if link.user != user:
			_refuse(_("This identity is linked to a different user."))
	else:
		other = frappe.db.get_value(LINK_DOCTYPE, {"issuer": issuer, "user": user}, "subject")
		if other:
			_refuse(_("This user is already linked to a different identity."))
		if not helpers.email_verified(claims):
			_refuse(_("The e-mail address is not verified by the identity provider."))
		create_link(issuer, subject, user)

	frappe.flags[SESSION_FLAG] = helpers.session_claims(claims, issuer)


def on_session_creation(login_manager=None) -> None:
	"""Stores the Keycloak session id in the Frappe session record. The logout token is matched against it."""
	data = frappe.flags.pop(SESSION_FLAG, None)
	if not data or frappe.session.user == "Guest":
		return
	frappe.local.session.data.update(data)
	frappe.local.session_obj.update(force=True)


def create_link(issuer: str, subject: str, user: str):
	"""Creates the identity link.

	G-4: `ignore_permissions` is justified because the request runs as Guest and the target user comes from
	the identity provider's verified e-mail, not from client input.
	"""
	doc = frappe.new_doc(LINK_DOCTYPE)
	doc.update({"issuer": issuer, "subject": subject, "user": user})
	doc.insert(ignore_permissions=True)
	return doc


def _refuse(message: str) -> None:
	frappe.throw(message, frappe.PermissionError)
