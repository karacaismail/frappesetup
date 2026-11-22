"""AU-19: once Keycloak sign-in works for administrators too, Frappe's password and e-mail link sign-ins are closed.

The gate is the site setting `kimlik_yalniz_keycloak`. The way back is documented in kimlik/README.md.
A-7: the built-in portal pages are closed to end users (“Website User”).
"""

import frappe
from frappe import _

from platform_core.kimlik import site_settings

EMAIL_LINK_PATHS = (
	"/api/method/frappe.www.login.send_login_link",
	"/api/method/frappe.www.login.login_via_key",
)
PORTAL_PATHS = ("/me", "/update-profile", "/update-password", "/third_party_apps", "/billing", "/portal")


def before_login(login_manager=None) -> None:
	"""Runs at the start of `LoginManager.login` (frappe/auth.py:152). Stops password sign-in."""
	if site_settings.keycloak_only():
		frappe.throw(
			_("Password sign-in is disabled. Sign in with the identity provider."), frappe.AuthenticationError
		)


def before_request() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None:
		return
	path = request.path.rstrip("/") or "/"
	if site_settings.keycloak_only() and path in EMAIL_LINK_PATHS:
		frappe.throw(
			_("E-mail link sign-in is disabled. Sign in with the identity provider."), frappe.PermissionError
		)
	if _is_end_user() and _is_portal_path(path):
		frappe.throw(_("This page is not available. Use the application."), frappe.PermissionError)


def _is_end_user() -> bool:
	session = getattr(frappe.local, "session", None)
	if not session or session.user in ("", "Guest"):
		return False
	return session.data.get("user_type") == "Website User"


def _is_portal_path(path: str) -> bool:
	return any(path == root or path.startswith(root + "/") for root in PORTAL_PATHS)
