import frappe
from frappe import _
from frappe.api import API_URL_MAP, v1, v2
from frappe.core.doctype.server_script.server_script_utils import get_server_script_map
from frappe.handler import get_attr, run_doc_method
from frappe.modules.utils import load_doctype_module
from werkzeug.exceptions import Forbidden, HTTPException
from werkzeug.utils import redirect

from press_tr.kimlik.service import SERVICE_PARAMETERS

LEGACY_PAGES = frozenset({"/login", "/signup", "/dashboard/login"})
GUEST_METHODS = (
	"ping",
	"press_tr.api.auth.get_login_url",
	"press_tr.api.auth.keycloak_callback",
	"press_tr.api.keycloak_backchannel_logout",
)
API_PREFIXES = ("/api/method/", "/api/v1/method/", "/api/v2/method/")
ADMIN_METHOD = "press_tr.api.maintenance.cleanup_expired_sessions"


def block_native_login(login_manager=None):
	raise Forbidden()


def resolve_method(name):
	if not isinstance(name, str):
		return None
	try:
		name = frappe.override_whitelisted_method(name)
		if name in get_server_script_map().get("_api", {}):
			return None
		target = get_attr(name)
		return target if callable(target) else None
	except AttributeError, ImportError, KeyError, frappe.DoesNotExistError, frappe.PermissionError:
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
	except HTTPException, ImportError, frappe.DoesNotExistError, frappe.PermissionError:
		return None, {}


def allowed_guest_targets():
	return {frappe.ping, *(frappe.get_attr(name) for name in GUEST_METHODS if name != "ping")}


def block_team_invitation(target, arguments):
	from press.api.account import accept_team_invite, setup_account
	from press.api.client import run_doc_method as run_press_doc_method
	from press.press.doctype.team.team import Team

	if target in {accept_team_invite, setup_account, Team.invite_team_member}:
		raise Forbidden()

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
		raise Forbidden()


def before_request():
	path = frappe.request.path.rstrip("/")
	if path in LEGACY_PAGES:
		panel_url = frappe.conf.platform_panel_url
		if not panel_url:
			raise Forbidden()
		raise HTTPException(response=redirect(panel_url))

	target, arguments = request_target()
	if arguments is None:
		return
	frappe.local.press_request_target = (target, arguments)
	block_team_invitation(target, arguments)

	# Keep Press's allowlist bounded to the documented routes.
	from press.auth import ALLOWED_PATHS

	routes = {prefix + name for prefix in API_PREFIXES for name in GUEST_METHODS}
	routes.update(f"/api/method/{name}" for name in (*SERVICE_PARAMETERS, ADMIN_METHOD))
	if path in routes and path not in ALLOWED_PATHS:
		ALLOWED_PATHS.append(path)

	if not frappe.get_request_header("Authorization"):
		enforce_guest_allowlist()


def enforce_guest_allowlist():
	target = getattr(frappe.local, "press_request_target", None)
	if target is not None and frappe.session.user == "Guest" and target[0] not in allowed_guest_targets():
		frappe.throw(_("Guest access is denied."), frappe.PermissionError)
