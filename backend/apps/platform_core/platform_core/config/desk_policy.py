"""G-53: only platform operators open the Desk. Every other signed-in user is sent to the panel.

Frappe has no setting that keeps a System User away from the Desk, so a request hook does it.
The settings below turn off Desk notices and make the panel the site's home page.
"""

import frappe
from frappe.core.doctype.system_settings.system_settings import clear_system_settings_cache
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect

OPERATOR_ROLE = "Platform Operator"
PANEL_ROUTE = "panel"
PANEL_PATH = "/" + PANEL_ROUTE
DESK_ROOTS = ("app", "desk")
SYSTEM_SETTINGS = {
	"enable_onboarding": 0,
	"disable_system_update_notification": 1,
	"disable_change_log_notification": 1,
}
WEBSITE_SETTINGS = {"home_page": PANEL_ROUTE}


def is_desk_path(path: str) -> bool:
	"""True for /app, /desk and every page below them. Similar names such as /apple do not match.

	The check copies Frappe's own path rules (`frappe/website/path_resolver.py`): strip "/" and
	spaces at both ends, then drop a trailing ".html". So /desk/.., /desk%20 and /desk.html match.
	"""
	path = (path or "").strip("/ ")
	if path.endswith(".html"):
		path = path[: -len(".html")]
	return any(path == root or path.startswith(root + "/") for root in DESK_ROOTS)


def before_request() -> None:
	"""Cookie sessions. Frappe runs this hook before it reads API keys and tokens."""
	_send_to_panel()


def after_auth() -> None:
	"""API keys and OAuth tokens. Frappe runs `auth_hooks` after it knows the user."""
	_send_to_panel()


def _send_to_panel() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None or request.method == "OPTIONS" or not is_desk_path(request.path):
		return
	user = frappe.session.user
	# A guest signs in first. Frappe's sign-in redirect then reaches this hook again.
	if user == "Guest" or OPERATOR_ROLE in frappe.get_roles(user):
		return
	# 302, not 301: the answer depends on the user's roles, and browsers keep a 301.
	raise HTTPException(response=redirect(PANEL_PATH, 302))


def apply(_args=None) -> None:
	"""Write the G-53 settings on install and after every migration."""
	if _update("System Settings", SYSTEM_SETTINGS):
		clear_system_settings_cache()
	if _update("Website Settings", WEBSITE_SETTINGS):
		frappe.cache.delete_value("home_page")


def _update(doctype: str, values: dict) -> bool:
	changes = {
		field: value for field, value in values.items() if frappe.db.get_single_value(doctype, field) != value
	}
	if changes:
		# A full save could rewrite unrelated settings, so only the changed fields are written.
		frappe.db.set_single_value(doctype, changes)
	return bool(changes)
