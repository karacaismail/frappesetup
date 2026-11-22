"""Cookie-authenticated mobile sync for the same-origin PWA."""

import frappe

from platform_core.mobil.request import pwa_endpoint_response

from .mobile import _activity, _list_installations, _pull, _push, _register, _revoke, _revoke_installation


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_register():
	return pwa_endpoint_response("v1_register", _register)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_revoke():
	return pwa_endpoint_response("v1_revoke", _revoke)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_activity():
	return pwa_endpoint_response("v1_activity", _activity)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_push():
	return pwa_endpoint_response("v1_push", _push)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_pull():
	return pwa_endpoint_response("v1_pull", _pull)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_list_installations():
	return pwa_endpoint_response("v1_list_installations", _list_installations)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_revoke_installation():
	return pwa_endpoint_response("v1_revoke_installation", _revoke_installation)
