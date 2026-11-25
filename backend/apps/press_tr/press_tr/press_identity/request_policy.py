import frappe
from frappe import _
from frappe.api import API_URL_MAP, v1, v2
from frappe.core.doctype.server_script.server_script_utils import get_server_script_map
from frappe.handler import get_attr, run_doc_method
from frappe.integrations import oauth2_logins
from frappe.modules.utils import load_doctype_module
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect

from press_tr.press_identity.deletion import ACCOUNT_DELETION_PAGE
from press_tr.press_identity.machine_routes import MACHINE_METHODS, MONITORING_ALERT, machine_targets
from press_tr.press_identity.service import SERVICE_PARAMETERS

LEGACY_PAGES = frozenset({"/login", "/signup", "/dashboard/login"})
GUEST_METHODS = (
	"ping",
	"press_tr.api.auth.get_login_url",
	"press_tr.api.auth.keycloak_callback",
	"press_tr.api.keycloak_backchannel_logout",
	# G-163: a person who lost their key cannot sign in. The method is rate limited and gives the
	# same answer for every address.
	"press_tr.api.account.request_recovery",
)
LOCAL_IDENTITY_METHODS = (
	"frappe.core.doctype.user.user.sign_up",
	"frappe.core.doctype.user.user.reset_password",
	"frappe.core.doctype.user.user.update_password",
	"frappe.www.login.login_via_token",
	"frappe.www.login.login_via_key",
	"frappe.www.login.send_login_link",
	"press.api.account.signup",
	"press.api.account.setup_account",
	"press.api.account.send_otp",
	"press.api.account.verify_otp",
	"press.api.account.verify_otp_and_login",
	"press.api.account.send_login_link",
	"press.api.account.login_using_key",
	"press.api.account.send_reset_password_email",
	"press.api.account.get_user_for_reset_password_key",
	"press.api.account.reset_password",
	"press.api.account.enable_2fa",
	"press.api.account.verify_2fa",
	"press.api.product_trial.send_verification_code_for_login",
	"press.api.product_trial.setup_account",
	"press.api.developer.saas.send_verification_code",
	"press.api.developer.saas.verify_verification_code",
	"press.api.developer.saas.login_to_fc",
	"press.api.saas.account_request",
	"press.api.saas.setup_account",
	"press.api.saas.headless_setup_account",
	"press.api.saas.get_site_url_and_sid",
	"press.api.google.login",
	"press.api.google.callback",
	"press.api.oauth.callback",
	"press.api.oauth.saas_setup",
	"press.api.marketplace.login_via_token",
)
API_PREFIXES = ("/api/method/", "/api/v1/method/", "/api/v2/method/")
# Desk methods for a System Manager. They answer only on Tailscale.
ADMIN_METHOD = (
	"press_tr.api.maintenance.cleanup_expired_sessions",
	# AJA-420: a reviewer removes the old keys after an approved recovery.
	"press_tr.api.account.remove_recovered_keys",
)
ACCOUNT_METHOD = "press_tr.api.account.request_deletion"


def deny_request():
	frappe.throw(_("This Press request is not allowed.", context="press_tr"), frappe.PermissionError)


def block_native_login(login_manager=None):
	deny_request()


def resolve_method(name):
	if not isinstance(name, str):
		return None
	try:
		name = frappe.override_whitelisted_method(name)
		if name in get_server_script_map().get("_api", {}):
			return None
		target = get_attr(name)
		return target if callable(target) else None
	except (
		AttributeError,
		ImportError,
		KeyError,
		frappe.DoesNotExistError,
		frappe.PermissionError,
		frappe.ValidationError,
	):
		return None


def request_target():
	command = frappe.form_dict.get("cmd")
	if command:
		return resolve_method(command), {}
	if not frappe.request.path.startswith("/api/"):
		return None, None
	try:
		endpoint, arguments = API_URL_MAP.bind_to_environ(frappe.request.environ).match()
		method = arguments.get("method")
		if endpoint is v1.handle_rpc_call:
			return resolve_method(method.partition("/")[0]), {}
		if endpoint is v2.handle_rpc_call:
			if doctype := arguments.get("doctype"):
				method = f"{load_doctype_module(doctype).__name__}.{method}"
			return resolve_method(method), {}
		if frappe.request.path == "/api/v2/method/run_doc_method":
			return v2.run_doc_method, arguments
		return endpoint, arguments
	except (HTTPException, ImportError, frappe.DoesNotExistError, frappe.PermissionError):
		return None, {}


def allowed_guest_targets():
	return {frappe.ping, *(frappe.get_attr(name) for name in GUEST_METHODS if name != "ping")}


def blocked_identity_targets():
	local = {frappe.get_attr(name) for name in LOCAL_IDENTITY_METHODS}
	social = {
		value
		for value in vars(oauth2_logins).values()
		if callable(value) and getattr(value, "__module__", None) == oauth2_logins.__name__
	}
	return local | social


def block_team_invitation(target, arguments):
	from press.api.account import accept_team_invite, setup_account
	from press.api.client import run_doc_method as run_press_doc_method
	from press.press.doctype.team.team import Team

	if target in {accept_team_invite, setup_account, Team.invite_team_member}:
		deny_request()

	form = frappe.form_dict
	if target in {run_press_doc_method, run_doc_method}:
		doctype, method = form.get("dt"), form.get("method")
	elif target in {v1.execute_doc_method, v2.execute_doc_method}:
		doctype, method = arguments.get("doctype"), arguments.get("method") or form.get("run_method")
	elif target is v2.run_doc_method:
		document = form.get("document")
		if isinstance(document, str):
			try:
				document = frappe.parse_json(document)
			except ValueError:
				return
		doctype, method = document.get("doctype") if isinstance(document, dict) else None, form.get("method")
	else:
		return
	if (
		doctype == "Team"
		and isinstance(method, str)
		and getattr(Team, method, None) is Team.invite_team_member
	):
		deny_request()


def reject_mismatched_command(path):
	# Frappe 16 runs a "cmd" field before it reads the path (frappe/app.py). The edge proxy opens
	# only a few paths to customers (O-55), so a "cmd" must name the method of its own path.
	command = frappe.form_dict.get("cmd")
	if command and path not in {prefix + str(command) for prefix in API_PREFIXES}:
		deny_request()


def before_request():
	path = frappe.request.path.rstrip("/")
	reject_mismatched_command(path)
	if path == ACCOUNT_DELETION_PAGE:
		frappe.local.no_cache = True
		frappe.local.response_headers["Cache-Control"] = "private, no-store"
	if path in LEGACY_PAGES:
		panel_url = frappe.conf.platform_panel_url
		if not panel_url:
			deny_request()
		raise HTTPException(response=redirect(panel_url))

	target, arguments = request_target()
	if arguments is None:
		return
	frappe.local.press_request_target = (target, arguments)
	if target in blocked_identity_targets():
		deny_request()
	machine_method = machine_targets().get(target)
	if machine_method == MONITORING_ALERT and not frappe.request.args.get("webhook_token"):
		deny_request()
	block_team_invitation(target, arguments)

	# Keep Press's allowlist bounded to the documented routes.
	from press.auth import ALLOWED_PATHS

	routes = {prefix + name for prefix in API_PREFIXES for name in GUEST_METHODS}
	routes.update(
		f"/api/method/{name}"
		for name in (*SERVICE_PARAMETERS, *MACHINE_METHODS, *ADMIN_METHOD, ACCOUNT_METHOD)
	)
	if path in routes and path not in ALLOWED_PATHS:
		ALLOWED_PATHS.append(path)

	if not frappe.get_request_header("Authorization"):
		enforce_guest_allowlist()


def enforce_guest_allowlist():
	target = getattr(frappe.local, "press_request_target", None)
	if target is None or frappe.session.user != "Guest":
		return
	if target[0] not in allowed_guest_targets() and target[0] not in machine_targets():
		frappe.throw(_("Guest access is denied.", context="press_tr"), frappe.PermissionError)
