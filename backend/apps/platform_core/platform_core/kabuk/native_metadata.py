"""Enforce the Website User RPC allowlist after Frappe resolves the request."""

import frappe
from frappe.api import API_URL_MAP, v1, v2
from frappe.core.doctype.server_script.server_script_utils import get_server_script_map
from frappe.handler import get_attr as get_legacy_attr
from frappe.handler import logout as legacy_logout
from frappe.modules.utils import load_doctype_module
from frappe.permissions import is_system_user
from werkzeug.exceptions import HTTPException

V1_RPC = v1.handle_rpc_call
V2_RPC = v2.handle_rpc_call
V2_LOGOUT = v2.logout
V2_META = v2.get_meta
SEARCH_LINK = "frappe.desk.search.search_link"
GUARDED_SEARCH_LINK = "platform_core.erisim.link_search.search_link"
SERVER_SCRIPT = object()
LEGACY_LOGIN = object()


def guard_website_rpc_before_request() -> None:
	"""Check cookie requests before dispatch; auth hooks check the final identity."""
	if frappe.session.user != "Guest" and not frappe.get_request_header("Authorization"):
		guard_native_metadata()


def guard_native_metadata() -> None:
	request = frappe.local.request
	command = frappe.form_dict.get("cmd")
	if request.method == "OPTIONS" or (not command and not request.path.startswith("/api/")):
		return
	if is_system_user():
		return

	target = resolve_request_target(request, command)
	# HTTPRequest has already authenticated the two legacy login forms.
	legacy_login = command == "login" or (not command and request.path == "/api/method/login")
	if target is None or (target is LEGACY_LOGIN and legacy_login):
		return
	if target is V2_META or (frappe.session.user != "Guest" and not website_method_allowed(target)):
		frappe.throw(frappe._("You are not permitted to call this method."), frappe.PermissionError)


def resolve_request_target(request, command):
	if command:
		return resolve_method(command, legacy=True)
	try:
		endpoint, arguments = API_URL_MAP.bind_to_environ(request.environ).match()
	except HTTPException:
		# Let the framework return its normal routing error.
		return None
	if endpoint is V1_RPC:
		return resolve_method(arguments["method"].split("/", 1)[0], legacy=True)
	if endpoint is V2_RPC:
		return resolve_method(arguments["method"], doctype=arguments.get("doctype"))
	if endpoint is V2_META or request.path.startswith("/api/v2/method/"):
		return endpoint
	return None


def resolve_method(method: str, *, legacy: bool = False, doctype: str | None = None):
	if legacy and method == "login":
		return LEGACY_LOGIN
	if doctype:
		try:
			module = load_doctype_module(doctype)
		except Exception:
			raise frappe.ValidationError("The requested method could not be resolved.") from None
		method = module.__name__ + "." + method

	if not isinstance(method, str):
		raise frappe.ValidationError("The requested method could not be resolved.")
	method = frappe.override_whitelisted_method(method)
	if get_server_script_map().get("_api", {}).get(method):
		return SERVER_SCRIPT

	get_method = get_legacy_attr if legacy else frappe.get_attr
	try:
		return get_method(method)
	except Exception:
		raise frappe.ValidationError("The requested method could not be resolved.") from None


def website_method_allowed(target) -> bool:
	for name in frappe.get_hooks("website_user_allowed_methods"):
		if name == "logout":
			if target is legacy_logout or target is V2_LOGOUT:
				return True
			continue
		if name == SEARCH_LINK:
			# The native implementation is outside the access-rule boundary.
			if frappe.override_whitelisted_method(SEARCH_LINK) != GUARDED_SEARCH_LINK:
				continue
			name = GUARDED_SEARCH_LINK
		if target is frappe.get_attr(name):
			return True
	return False
