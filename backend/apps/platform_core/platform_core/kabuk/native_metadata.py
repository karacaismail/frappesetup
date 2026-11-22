"""Deny native unfiltered metadata to accounts without system access."""

import frappe
from frappe.api import API_URL_MAP
from frappe.api.v2 import get_meta
from frappe.permissions import is_system_user
from werkzeug.exceptions import HTTPException


def guard_native_metadata() -> None:
	request = frappe.local.request
	if not request.path.startswith("/api/v2/doctype/"):
		return
	try:
		endpoint, _ = API_URL_MAP.bind_to_environ(request.environ).match()
	except HTTPException:
		# Frappe handles routing errors and redirects itself.
		return
	if endpoint is get_meta and not is_system_user():
		frappe.throw(frappe._("You cannot read this DocType."), frappe.PermissionError)
