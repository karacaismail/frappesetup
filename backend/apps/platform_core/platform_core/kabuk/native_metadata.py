"""Deny native unfiltered metadata to accounts without system access."""

import frappe
from frappe.api import API_URL_MAP, v1, v2
from frappe.desk.form.load import getdoctype
from frappe.handler import get_attr as get_legacy_attr
from frappe.modules.utils import load_doctype_module
from frappe.permissions import is_system_user
from werkzeug.exceptions import HTTPException

BLOCKED_METADATA = (getdoctype, v2.get_meta)


def guard_native_metadata() -> None:
	request = frappe.local.request
	command = frappe.form_dict.get("cmd")
	if request.method == "OPTIONS" or (not command and not request.path.startswith("/api/")):
		return
	if is_system_user():
		return
	target = resolve_request_target(request, command)
	if any(target is blocked for blocked in BLOCKED_METADATA):
		frappe.throw(
			frappe._("You cannot read this DocType.", context="shell.metadata"), frappe.PermissionError
		)


def resolve_request_target(request, command):
	try:
		if command:
			return resolve_legacy_target(command)
		endpoint, arguments = API_URL_MAP.bind_to_environ(request.environ).match()
		if endpoint is v1.handle_rpc_call:
			method = arguments["method"].split("/", 1)[0]
			return resolve_legacy_target(method)
		if endpoint is v2.handle_rpc_call:
			method = arguments["method"]
			if doctype := arguments.get("doctype"):
				method = load_doctype_module(doctype).__name__ + "." + method
			return frappe.get_attr(frappe.override_whitelisted_method(method))
		return endpoint
	except (
		HTTPException,
		ImportError,
		AttributeError,
		frappe.AppNotInstalledError,
		frappe.DoesNotExistError,
	):
		# Frappe reports its own routing and method errors.
		return None


def resolve_legacy_target(method: str):
	# Frappe handles login in HTTPRequest before the legacy handler.
	if method == "login":
		return None
	return get_legacy_attr(frappe.override_whitelisted_method(method))
