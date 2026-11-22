"""Tenant model gateway HTTP entry points."""

import frappe

from platform_core.model_gecidi import gateway


def _respond(call, *args):
	try:
		return call(*args)
	except gateway.Denied as failure:
		frappe.local.response.http_status_code = failure.status
		return {"error": failure.code}


# Access to a route is checked by gateway.complete and policy.require_route.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def complete(route, messages, tools=None, schema=None, limit=1024):
	"""Generate a response through one tenant route. Provider use may incur a charge."""
	return _respond(gateway.complete, route, messages, tools, schema, limit)


# gateway.test_api requires a human session and the registry-manager role.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def test_api(api, model):
	"""Send one bounded, billable test request as an AI or site manager."""
	return _respond(gateway.test_api, api, model)
