"""Tenant model gateway HTTP entry points."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

import frappe

from platform_core.model_gateway import api, connections, gateway, maintenance, policy


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
	fields: NotRequired[list[str]]


class CatalogField(TypedDict):
	name: str
	label: str
	kind: Literal["secret", "text", "url"]
	required: bool
	scope: Literal["account", "api"]
	description: str


class CatalogCategory(TypedDict):
	id: str
	label: str
	description: str


class CatalogProvider(TypedDict):
	id: str
	category: str
	label: str
	description: str
	auth_type: Literal["none", "api_key", "bearer", "oauth_client_credentials"]
	fields: list[CatalogField]
	common_fields: list[CatalogField]


class ProviderCatalog(TypedDict):
	version: int
	categories: list[CatalogCategory]
	providers: list[CatalogProvider]


class SavedConnection(TypedDict):
	provider: str
	account: str
	api: str
	connection_status: Literal["not_checked"]


class ConnectionCheck(TypedDict):
	api: str
	status: str
	checked_at: str
	models_visible: int | None


class FileJobCreated(TypedDict):
	name: str


class FileJobChunk(TypedDict):
	index: int
	first_page: int
	last_page: int
	byte_count: int
	status: Literal["planned", "queued", "running", "done", "failed"]
	failure_code: str | None


class FileJobStatus(TypedDict):
	name: str
	status: Literal["preparing", "planned", "queued", "running", "completed", "failed"]
	failure_code: str | None
	chunk_count: int | None
	estimated_cost: str | None
	currency: str | None
	chunks: list[FileJobChunk]


class FileJobQueued(TypedDict):
	name: str
	status: Literal["queued"]


class FileChunkQueued(TypedDict):
	name: str
	chunk_index: int
	status: Literal["queued"]


def _respond(call, *args, allow_api_key=False):
	try:
		policy.require_session(allow_api_key=allow_api_key)
		return call(*args)
	except policy.Denied as failure:
		# Frappe commits a POST whose handler returns normally, even on an error status.
		if getattr(frappe.local, "request", None) is not None:
			frappe.db.rollback(chain=True)
		frappe.local.response.http_status_code = failure.status
		fields = getattr(failure, "fields", None)
		return {"error": failure.code, "fields": fields} if fields else {"error": failure.code}


# Defer annotations so Frappe leaves JSON values to the gateway's strict validators.
# Eager validation could coerce malformed input or change the HTTP error response.
# Access to a route is checked by gateway.complete and policy.require_route.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
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
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def test_api(api: str, model: str) -> CompletionResult | ErrorResponse:
	"""Send one bounded, billable test request as an AI or site manager."""
	return _respond(gateway.test_api, api, model)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def resolve_usage(
	log: str, cost: str, currency: str | None = None, note: str | None = None
) -> ResolvedUsage | ErrorResponse:
	"""Reconcile a model attempt with its verified cost."""
	return _respond(maintenance.resolve_usage, log, cost, currency, note)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def reconcile_stale_pending() -> ReconciledPending | ErrorResponse:
	"""Close expired reservations as unknown without releasing reserved cost."""
	return _respond(maintenance.reconcile_stale_pending)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def purge_usage(dry_run: bool = True, preview_token: str | None = None) -> PurgedUsage | ErrorResponse:
	"""Preview or delete closed usage records beyond the fixed 365-day retention window."""
	return _respond(maintenance.purge_usage, dry_run, preview_token)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def clear_api_credential(api: str) -> ClearedCredential | ErrorResponse:
	"""Remove the credential of a disabled API connection."""
	return _respond(maintenance.clear_api_credential, api)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def provider_catalog() -> ProviderCatalog | ErrorResponse:
	"""List the provider definitions the connection form draws from, for AI or site managers."""
	return _respond(connections.provider_catalog)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def save_connection(
	provider: str,
	api_name: str,
	fields: dict[str, str],
	account: str | None = None,
	account_name: str | None = None,
) -> SavedConnection | ErrorResponse:
	"""Save a new API connection from a provider definition. Secrets are stored encrypted."""
	return _respond(connections.save_connection, provider, api_name, fields, account, account_name)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def check_connection(api: str) -> ConnectionCheck | ErrorResponse:
	"""Check a saved connection with one model-list request and record the result."""
	return _respond(connections.check_connection, api)


# Large file jobs (G-156). The service checks the route, the file and the job owner.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def create_file_job(
	route: str, file: str, instruction: str, limit: int = 1024
) -> FileJobCreated | ErrorResponse:
	"""Record a large PDF job and queue its page text step. No provider is called."""
	return _respond(lambda: {"name": api.create_file_job(route, file, instruction, limit)})


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def file_job_status(file_job: str) -> FileJobStatus | ErrorResponse:
	"""Show the chunk plan, the cost estimate and the progress of the caller's job."""
	return _respond(api.file_job_status, file_job)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def start_file_job(file_job: str) -> FileJobQueued | ErrorResponse:
	"""Queue every planned chunk. Each chunk is a separate, possibly billable gateway call."""

	def start():
		api.start_file_job(file_job)
		return {"name": file_job, "status": "queued"}

	return _respond(start)


@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def retry_file_chunk(file_job: str, chunk_index: int) -> FileChunkQueued | ErrorResponse:
	"""Queue one failed chunk again. Finished chunks are not sent again."""

	def retry():
		api.retry_file_chunk(file_job, chunk_index)
		return {"name": file_job, "chunk_index": chunk_index, "status": "queued"}

	return _respond(retry)
