"""Tenant model gateway HTTP entry points."""

import frappe

from platform_core.model_gecidi import gateway, maintenance, policy


def _respond(call, *args, allow_api_key=False):
	try:
		policy.require_session(allow_api_key=allow_api_key)
		return call(*args)
	except policy.Denied as failure:
		frappe.local.response.http_status_code = failure.status
		return {"error": failure.code}


# Access to a route is checked by gateway.complete and policy.require_route.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def complete(route, messages, tools=None, schema=None, limit=1024):
	"""Generate a response through one tenant route. Provider use may incur a charge."""
	return _respond(gateway.complete, route, messages, tools, schema, limit, allow_api_key=True)


# Gateway operations check manager permissions and record access in the service layer.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def test_api(api, model):
	"""Send one bounded, billable test request as an AI or site manager."""
	return _respond(gateway.test_api, api, model)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def resolve_usage(log, cost):
	"""Reconcile a model attempt with its verified cost."""
	return _respond(maintenance.resolve_usage, log, cost)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def purge_usage(dry_run=True):
	"""Preview or delete closed usage records beyond the configured retention window."""
	return _respond(maintenance.purge_usage, dry_run)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def clear_api_credential(api):
	"""Remove the credential of a disabled API connection."""
	return _respond(maintenance.clear_api_credential, api)
