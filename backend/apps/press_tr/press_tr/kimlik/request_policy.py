import frappe
from werkzeug.exceptions import Forbidden, HTTPException
from werkzeug.utils import redirect

from press_tr.kimlik.service import SERVICE_PARAMETERS

CLOSED_METHODS = frozenset(
	{
		"press.api.account.signup",
		"press.api.account.send_otp",
		"press.api.account.verify_otp",
		"press.api.account.verify_otp_and_login",
		"press.api.account.send_login_link",
		"press.api.account.login_using_key",
		"press.api.account.reset_password",
		"press.api.account.enable_2fa",
		"press.api.account.verify_2fa",
		"press.api.product_trial.send_verification_code_for_login",
	}
)
LEGACY_PAGES = frozenset({"/login", "/signup", "/dashboard/login"})
API_PREFIXES = ("/api/method/", "/api/v1/method/", "/api/v2/method/")
APP_METHODS = frozenset(
	{
		"press_tr.api.auth.get_login_url",
		"press_tr.api.auth.keycloak_callback",
		"press_tr.api.keycloak_backchannel_logout",
	}
)


def before_request():
	path = frappe.request.path.rstrip("/")
	command = frappe.form_dict.get("cmd")
	if (isinstance(command, str) and command in CLOSED_METHODS) or any(
		path.startswith(prefix) and path[len(prefix) :] in CLOSED_METHODS for prefix in API_PREFIXES
	):
		raise Forbidden()
	if path in LEGACY_PAGES:
		panel_url = frappe.conf.platform_panel_url
		if not panel_url:
			raise Forbidden()
		raise HTTPException(response=redirect(panel_url))

	# Press denies non-Press API paths by default. Extend its runtime allowlist
	# with the exact methods exposed here, without editing its source.
	if path.removeprefix("/api/method/") in APP_METHODS | SERVICE_PARAMETERS.keys():
		allow_press_route(path)


def allow_press_route(path):
	from press.auth import ALLOWED_PATHS

	if path not in ALLOWED_PATHS:
		ALLOWED_PATHS.append(path)
