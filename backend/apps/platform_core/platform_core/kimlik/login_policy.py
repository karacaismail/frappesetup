"""AU-19: once Keycloak sign-in works for administrators too, Frappe's local sign-in paths are closed.

The gate is the site setting `kimlik_yalniz_keycloak`. The way back is documented in kimlik/README.md.
The gate is applied to the called function, not to one URL spelling: `override_whitelisted_methods`
replaces every local sign-in function with a gated wrapper (frappe/__init__.py:1577), so `/api/method`,
`/api/v1/method`, `/api/v2/method` and `cmd` requests are all covered. Password sign-in itself goes
through `LoginManager.login`, which runs the `before_login` trigger (frappe/auth.py:152).
A-7: the built-in portal pages are closed to end users (“Website User”).
"""

import frappe
from frappe import _

from platform_core.kimlik import helpers, site_settings

PORTAL_PATHS = ("/me", "/update-profile", "/update-password", "/third_party_apps", "/billing", "/portal")
GATE_MESSAGE = "Local sign-in is disabled. Sign in with the identity provider."


def before_login(login_manager=None) -> None:
	"""Runs at the start of `LoginManager.login`. Stops password sign-in while the gate is on."""
	if site_settings.keycloak_only():
		frappe.throw(_("Password sign-in is disabled. Sign in with the identity provider."), frappe.AuthenticationError)


def before_request() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None:
		return
	if _is_end_user() and _is_portal_path(helpers.normalize_path(request.path)):
		frappe.throw(_("This page is not available. Use the application."), frappe.PermissionError)


def _is_end_user() -> bool:
	session = getattr(frappe.local, "session", None)
	if not session or session.user in ("", "Guest"):
		return False
	return session.data.get("user_type") == "Website User"


def _is_portal_path(path: str) -> bool:
	return any(path == root or path.startswith(root + "/") for root in PORTAL_PATHS)


def _gated(original: str, name: str, methods: list[str] | None = None):
	"""Whitelisted wrapper: 403 while the gate is on, otherwise the original Frappe function."""

	@frappe.whitelist(allow_guest=True, methods=methods)
	def wrapper(*args, **kwargs):
		if site_settings.keycloak_only():
			frappe.throw(_(GATE_MESSAGE), frappe.PermissionError)
		return frappe.call(frappe.get_attr(original), *args, **kwargs)

	wrapper.__name__ = wrapper.__qualname__ = name
	wrapper.__doc__ = f"Gated wrapper of `{original}` (AU-19)."
	return wrapper


# HTTP methods mirror the originals (frappe/core/doctype/user/user.py, frappe/www/login.py,
# frappe/integrations/oauth2_logins.py) so that Frappe's method check behaves the same.
GATED_FUNCTIONS = {
	"frappe.core.doctype.user.user.reset_password": ("reset_password", ["POST"]),
	"frappe.core.doctype.user.user.update_password": ("update_password", ["POST"]),
	"frappe.core.doctype.user.user.sign_up": ("sign_up", None),
	"frappe.www.login.send_login_link": ("send_login_link", ["POST"]),
	"frappe.www.login.login_via_key": ("login_via_key", ["GET"]),
	"frappe.www.login.login_via_token": ("login_via_token", None),
	"frappe.integrations.oauth2_logins.login_via_google": ("login_via_google", None),
	"frappe.integrations.oauth2_logins.login_via_github": ("login_via_github", None),
	"frappe.integrations.oauth2_logins.login_via_facebook": ("login_via_facebook", None),
	"frappe.integrations.oauth2_logins.login_via_frappe": ("login_via_frappe", None),
	"frappe.integrations.oauth2_logins.login_via_office365": ("login_via_office365", None),
	"frappe.integrations.oauth2_logins.login_via_salesforce": ("login_via_salesforce", None),
	"frappe.integrations.oauth2_logins.login_via_fairlogin": ("login_via_fairlogin", None),
	"frappe.integrations.oauth2_logins.login_via_keycloak": ("login_via_keycloak", None),
	"frappe.integrations.oauth2_logins.custom": ("custom", None),
}

reset_password = _gated("frappe.core.doctype.user.user.reset_password", "reset_password", ["POST"])
update_password = _gated("frappe.core.doctype.user.user.update_password", "update_password", ["POST"])
sign_up = _gated("frappe.core.doctype.user.user.sign_up", "sign_up")
send_login_link = _gated("frappe.www.login.send_login_link", "send_login_link", ["POST"])
login_via_key = _gated("frappe.www.login.login_via_key", "login_via_key", ["GET"])
login_via_token = _gated("frappe.www.login.login_via_token", "login_via_token")
login_via_google = _gated("frappe.integrations.oauth2_logins.login_via_google", "login_via_google")
login_via_github = _gated("frappe.integrations.oauth2_logins.login_via_github", "login_via_github")
login_via_facebook = _gated("frappe.integrations.oauth2_logins.login_via_facebook", "login_via_facebook")
login_via_frappe = _gated("frappe.integrations.oauth2_logins.login_via_frappe", "login_via_frappe")
login_via_office365 = _gated("frappe.integrations.oauth2_logins.login_via_office365", "login_via_office365")
login_via_salesforce = _gated("frappe.integrations.oauth2_logins.login_via_salesforce", "login_via_salesforce")
login_via_fairlogin = _gated("frappe.integrations.oauth2_logins.login_via_fairlogin", "login_via_fairlogin")
login_via_keycloak = _gated("frappe.integrations.oauth2_logins.login_via_keycloak", "login_via_keycloak")
custom = _gated("frappe.integrations.oauth2_logins.custom", "custom")


def override_map() -> dict[str, str]:
	"""The `override_whitelisted_methods` entries, used by hooks_fragment.py and the tests."""
	return {original: f"{__name__}.{name}" for original, (name, _methods) in GATED_FUNCTIONS.items()}
