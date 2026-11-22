"""Tenant model gateway HTTP entry points."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

import frappe

from platform_core.model_gecidi import api, gateway, maintenance, policy


class CompletionMessage(TypedDict):
	role: Literal["system", "user", "assistant"]
	content: str


class OfferedTool(TypedDict):
	name: str
	parameters: dict[str, object]
	description: NotRequired[str]


class ToolCall(TypedDict):
	id: str
	name: str
	arguments: dict[str, object]


class TokenUsage(TypedDict):
	input: int | None
	output: int | None


class CompletionResult(TypedDict):
	text: str
	tool_calls: list[ToolCall]
	usage: TokenUsage
	model: str
	api: str


class ResolvedUsage(TypedDict):
	name: str
	result: Literal["resolved"]
	cost: str
	currency: str


class PurgedUsage(TypedDict):
	eligible: int
	deleted: int
	dry_run: bool
	targets: list[str]
	preview_token: str | None


class ReconciledPending(TypedDict):
	closed: int
	targets: list[str]


class ClearedCredential(TypedDict):
	name: str
	cleared: Literal[True]


class ErrorResponse(TypedDict):
	error: str


def _respond(call, *args, allow_api_key=False):
	try:
		policy.require_session(allow_api_key=allow_api_key)
		return call(*args)
	except policy.Denied as failure:
		# Frappe commits a POST whose handler returns normally, even on an error status.
		if getattr(frappe.local, "request", None) is not None:
			frappe.db.rollback(chain=True)
		frappe.local.response.http_status_code = failure.status
		return {"error": failure.code}


# Defer annotations so Frappe leaves JSON values to the gateway's strict validators.
# Eager validation could coerce malformed input or change the HTTP error response.
# Access to a route is checked by gateway.complete and policy.require_route.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def complete(
	route: str,
	messages: list[CompletionMessage],
	tools: list[OfferedTool] | None = None,
	schema: dict[str, object] | None = None,
	limit: int = 1024,
) -> CompletionResult | ErrorResponse:
	"""Generate a response through one tenant route. Provider use may incur a charge."""
	return _respond(api.complete, route, messages, tools, schema, limit, allow_api_key=True)


# Gateway operations check manager permissions and record access in the service layer.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def test_api(api: str, model: str) -> CompletionResult | ErrorResponse:
	"""Send one bounded, billable test request as an AI or site manager."""
	return _respond(gateway.test_api, api, model)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def resolve_usage(
	log: str, cost: str, currency: str | None = None, note: str | None = None
) -> ResolvedUsage | ErrorResponse:
	"""Reconcile a model attempt with its verified cost."""
	return _respond(maintenance.resolve_usage, log, cost, currency, note)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def reconcile_stale_pending() -> ReconciledPending | ErrorResponse:
	"""Close expired reservations as unknown without releasing reserved cost."""
	return _respond(maintenance.reconcile_stale_pending)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def purge_usage(dry_run: bool = True, preview_token: str | None = None) -> PurgedUsage | ErrorResponse:
	"""Preview or delete closed usage records beyond the fixed 365-day retention window."""
	return _respond(maintenance.purge_usage, dry_run, preview_token)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def clear_api_credential(api: str) -> ClearedCredential | ErrorResponse:
	"""Remove the credential of a disabled API connection."""
	return _respond(maintenance.clear_api_credential, api)
