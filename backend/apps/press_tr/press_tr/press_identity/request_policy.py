import frappe
from werkzeug.exceptions import Forbidden, HTTPException
from werkzeug.utils import redirect

from press_tr.press_identity.service import SERVICE_PARAMETERS

SOCIAL_PREFIX = "frappe.integrations.oauth2_logins."
SOCIAL_METHODS = {
	SOCIAL_PREFIX + name
	for name in (
		"login_via_google",
		"login_via_github",
		"login_via_facebook",
		"login_via_frappe",
		"login_via_office365",
		"login_via_salesforce",
		"login_via_fairlogin",
		"login_via_keycloak",
		"custom",
	)
}

CLOSED_METHODS = frozenset(
	{
		"frappe.core.doctype.user.user.sign_up",
		"frappe.core.doctype.user.user.reset_password",
		"frappe.core.doctype.user.user.update_password",
		"frappe.www.login.login_via_token",
		"frappe.www.login.login_via_key",
		"frappe.www.login.send_login_link",
		"press.api.account.setup_account",
		"press.api.account.send_reset_password_email",
		"press.api.account.get_user_for_reset_password_key",
		"press.api.oauth.google_oauth_flow",
		"press.api.oauth.google_login",
		"press.api.google.google_oauth_flow",
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


@frappe.whitelist(allow_guest=True)
def deny_legacy_method():
	raise Forbidden()


def block_native_login(login_manager=None):
	user = frappe.form_dict.get("usr")
	if not (
		frappe.conf.press_tr_allow_admin_password_login is True
		and user == "Administrator"
		and frappe.request.path == "/api/method/login"
	):
		raise Forbidden()


def closed_method(method):
	return method in CLOSED_METHODS or method.startswith(SOCIAL_PREFIX)


def rpc_method(path):
	for prefix in API_PREFIXES:
		if path.startswith(prefix):
			return path[len(prefix) :].partition("/")[0]
	return ""


def before_request():
	path = frappe.request.path.rstrip("/")
	command = frappe.form_dict.get("cmd")
	method = rpc_method(path)
	if (isinstance(command, str) and closed_method(command)) or closed_method(method):
		raise Forbidden()
	if method == "login" and path != "/api/method/login":
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
