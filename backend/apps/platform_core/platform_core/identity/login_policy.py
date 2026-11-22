"""AU-19: once Keycloak sign-in works for administrators too, Frappe's local sign-in paths are closed.

The gate is the site setting `kimlik_yalniz_keycloak`. The way back is documented in kimlik/README.md.
The gate is applied to the called function, not to one URL spelling: `override_whitelisted_methods`
replaces every local sign-in function with a gated wrapper (frappe/__init__.py:1577), so `/api/method`,
`/api/v1/method`, `/api/v2/method` and `cmd` requests are all covered. Password sign-in itself goes
through `LoginManager.login`, which runs the `before_login` trigger (frappe/auth.py:152).
A-7: the built-in portal pages are closed to end users (“Website User”).
"""

from inspect import signature

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.identity import helpers, site_settings
from platform_core.identity.exceptions import InvalidInput

PORTAL_PATHS = ("/me", "/update-profile", "/update-password", "/third_party_apps", "/billing", "/portal")
GUEST_LIMIT = 20
GUEST_WINDOW = 60


def before_login(login_manager=None) -> None:
	"""Runs at the start of `LoginManager.login`. Stops password sign-in while the gate is on."""
	if site_settings.keycloak_only():
		frappe.throw(
			_(
				"Password sign-in is disabled. Sign in with the identity provider.",
				context="platform_core.identity",
			),
			frappe.AuthenticationError,
		)


def before_request() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None:
		return
	if _is_end_user() and _is_portal_path(helpers.normalize_path(request.path)):
		frappe.throw(
			_("This page is not available. Use the application.", context="platform_core.identity"),
			frappe.PermissionError,
		)


def _is_end_user() -> bool:
	session = getattr(frappe.local, "session", None)
	if not session or session.user in ("", "Guest"):
		return False
	return session.data.get("user_type") == "Website User"


def _is_portal_path(path: str) -> bool:
	return any(path == root or path.startswith(root + "/") for root in PORTAL_PATHS)


def _call_gated(
	original: str, args: tuple, kwargs: dict, *, required_form_fields: tuple[str, ...] = ()
) -> object:
	"""403 while the gate is on, otherwise the original Frappe function with the same arguments."""
	from platform_core.identity.sign_in import guard_guest_request

	guard_guest_request()
	if site_settings.keycloak_only():
		frappe.throw(
			_(
				"Local sign-in is disabled. Sign in with the identity provider.",
				context="platform_core.identity",
			),
			frappe.PermissionError,
		)
	target = frappe.get_attr(original)
	forwarded = frappe.get_newargs(target, kwargs)
	try:
		signature(target).bind(*args, **forwarded)
		if any(not frappe.form_dict.get(field) for field in required_form_fields):
			raise ValueError("A required form field is missing")
	except (TypeError, ValueError):
		frappe.throw(
			_("Required sign-in arguments are missing.", context="platform_core.identity"),
			InvalidInput,
		)
	return target(*args, **forwarded)


# HTTP methods are explicit (review: Frappe opens GET, POST, PUT and DELETE when `methods` is missing).
# State-changing functions accept POST only (G-6). OAuth callbacks and link sign-in accept GET as their
# clients use it; `login_via_token` also accepts POST.
# LDAP sign-in calls `post_login` directly and skips `before_login` (ldap_settings.py:404), so it is gated here.
# The wrappers are written out one by one, so the AI readiness gate and the contract can see each endpoint.
GATED_FUNCTIONS = {
	"frappe.core.doctype.user.user.reset_password": ("reset_password", ["POST"]),
	"frappe.core.doctype.user.user.update_password": ("update_password", ["POST"]),
	"frappe.core.doctype.user.user.sign_up": ("sign_up", ["POST"]),
	"frappe.www.login.send_login_link": ("send_login_link", ["POST"]),
	"frappe.www.login.login_via_key": ("login_via_key", ["GET"]),
	"frappe.www.login.login_via_token": ("login_via_token", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_google": ("login_via_google", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_github": ("login_via_github", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_facebook": ("login_via_facebook", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_frappe": ("login_via_frappe", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_office365": ("login_via_office365", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_salesforce": ("login_via_salesforce", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_fairlogin": ("login_via_fairlogin", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.login_via_keycloak": ("login_via_keycloak", ["GET", "POST"]),
	"frappe.integrations.oauth2_logins.custom": ("custom", ["GET", "POST"]),
	"frappe.integrations.doctype.ldap_settings.ldap_settings.login": ("ldap_login", ["POST"]),
}


# These wrappers apply the site gate and then use the original Frappe credential checks.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def reset_password(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.core.doctype.user.user.reset_password` (AU-19)."""
	return _call_gated("frappe.core.doctype.user.user.reset_password", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def update_password(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.core.doctype.user.user.update_password` (AU-19)."""
	return _call_gated("frappe.core.doctype.user.user.update_password", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def sign_up(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.core.doctype.user.user.sign_up` (AU-19)."""
	return _call_gated("frappe.core.doctype.user.user.sign_up", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def send_login_link(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.www.login.send_login_link` (AU-19)."""
	return _call_gated("frappe.www.login.send_login_link", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_key(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.www.login.login_via_key` (AU-19)."""
	return _call_gated("frappe.www.login.login_via_key", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_token(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.www.login.login_via_token` (AU-19)."""
	return _call_gated("frappe.www.login.login_via_token", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_google(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_google` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_google", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_github(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_github` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_github", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_facebook(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_facebook` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_facebook", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_frappe(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_frappe` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_frappe", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_office365(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_office365` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_office365", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_salesforce(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_salesforce` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_salesforce", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_fairlogin(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_fairlogin` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_fairlogin", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def login_via_keycloak(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.login_via_keycloak` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.login_via_keycloak", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def custom(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.oauth2_logins.custom` (AU-19)."""
	return _call_gated("frappe.integrations.oauth2_logins.custom", args, kwargs)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=GUEST_LIMIT, seconds=GUEST_WINDOW)
def ldap_login(*args: object, **kwargs: object) -> object:
	"""Gated wrapper of `frappe.integrations.doctype.ldap_settings.ldap_settings.login` (AU-19)."""
	return _call_gated(
		"frappe.integrations.doctype.ldap_settings.ldap_settings.login",
		args,
		kwargs,
		required_form_fields=("usr", "pwd"),
	)


def override_map() -> dict[str, str]:
	"""The `override_whitelisted_methods` entries, as hooks.py lists them. The tests compare both."""
	return {original: f"{__name__}.{name}" for original, (name, _methods) in GATED_FUNCTIONS.items()}
