"""G-53: only platform operators open the Desk. Every other signed-in user is sent to the panel.

Frappe has no setting that keeps a System User away from the Desk, so a request hook does it.
The settings below turn off Desk notices and make the panel the site's home page.
"""

import frappe
from frappe.core.doctype.system_settings.system_settings import clear_system_settings_cache
from frappe.website.path_resolver import resolve_path
from werkzeug.exceptions import HTTPException
from werkzeug.routing.exceptions import RequestRedirect
from werkzeug.utils import redirect

OPERATOR_ROLE = "Platform Operator"
PANEL_ROUTE = "panel"
PANEL_PATH = "/" + PANEL_ROUTE
DESK_ROOTS = ("app", "desk")
# Frappe `app.py` sends a raw path with this prefix to the API handler, never to a page.
API_PREFIX = "/api/"
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

	A path with a "." or ".." part is also True (AJA-849). Frappe looks the page up with
	`os.path.join(app, "www", path)`, so /./desk and /../www/desk open `www/desk.html`.
	Frappe's API handler takes every raw path that starts with /api/, so those are left alone.
	"""
	raw = path or ""
	path = raw.strip("/ ")
	if path.endswith(".html"):
		path = path[: -len(".html")]
	if any(root == path or path.startswith(root + "/") for root in DESK_ROOTS):
		return True
	if raw.startswith(API_PREFIX):
		return False
	return any(part in (".", "..") for part in path.split("/"))


def before_request() -> None:
	"""Cookie sessions. Frappe runs this hook before it reads API keys and tokens."""
	_send_to_panel()


def after_auth() -> None:
	"""API keys and OAuth tokens. Frappe runs `auth_hooks` after it knows the user."""
	_send_to_panel()


def resolve_website_path(path: str) -> str:
	"""The `website_path_resolver` hook. It checks the page Frappe really picks (AJA-963).

	The request hooks only see the asked path. For /, /index and /index.html Frappe opens the
	user's home page instead. The home page is the Desk when a role's "Home Page" is "desk" or
	when the user has a default workspace. Route rules can also lead to the Desk.
	Frappe uses this hook in place of `resolve_path`, so the hook calls `resolve_path` itself.
	"""
	try:
		endpoint = resolve_path(path)
	except RequestRedirect as e:
		# Frappe handles this redirect only when no resolver hook is set, so it is done here.
		frappe.flags.redirect_location = e.new_url
		raise frappe.Redirect(e.code) from e
	if is_desk_path(endpoint) and _must_leave_desk():
		frappe.flags.redirect_location = PANEL_PATH
		raise frappe.Redirect(302)
	return endpoint


def _must_leave_desk() -> bool:
	"""The G-53 rule. A guest signs in first, and Frappe's sign-in redirect comes back here."""
	user = frappe.session.user
	return user != "Guest" and OPERATOR_ROLE not in frappe.get_roles(user)


def _send_to_panel() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None or request.method == "OPTIONS" or not is_desk_path(request.path):
		return
	if _must_leave_desk():
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
