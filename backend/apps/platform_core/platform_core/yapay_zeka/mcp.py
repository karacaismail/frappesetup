"""MCP endpoint: Streamable HTTP, single JSON response, no session.

Protocol parsing comes from Frappe's `frappe.mcp.transport` and `frappe.mcp.protocol`
modules. The tools, the identity rules and the log belong to this layer.
Decision: docs/kararlar/0002-yapay-zeka-katmani.md.
"""

import json
import time
from typing import Any

import frappe
from frappe import _
from frappe.mcp import protocol, transport
from frappe.mcp.protocol import METHOD_NOT_FOUND, McpError
from frappe.mcp.tools import validation_message
from frappe.utils import get_fullname, get_host_name, strip_html
from frappe.utils.response import json_handler
from pydantic import ValidationError
from werkzeug.wrappers import Response

from platform_core.yapay_zeka import access, agent_token, proposals, registry
from platform_core.yapay_zeka.errors import CONTEXT, ToolDenied

LIST_TTL_MS = 60000


def handle() -> Response:
	"""Answer one MCP request. A refusal of a known identity is logged before the error leaves.

	Errors propagate to `frappe.app`, which rolls the request back and answers in the MCP
	envelope. The log row is therefore committed here, before the error is raised again.
	At that point the request has written nothing else.
	"""
	frappe.local.mcp_request = transport.RequestContext()
	try:
		return _handle()
	except McpError as error:
		if not getattr(error, "logged", False) and access.principal() != access.GUEST:
			reason = getattr(error, "deny_reason", "protocol_error")
			stage = "auth" if reason == "origin_not_allowed" else "call"
			access.record_denial(stage, reason)
		raise


def _logged(error: McpError) -> McpError:
	"""Mark an error whose denial is already in the log, so that it is not logged twice."""
	error.logged = True
	return error


def _handle() -> Response:
	request = frappe.request
	context = frappe.local.mcp_request
	try:
		transport.check_origin(request)
	except McpError as error:
		error.deny_reason = "origin_not_allowed"
		raise
	_check_principal()
	if not request.is_json:
		raise McpError(protocol.INVALID_REQUEST, "Content-Type must be application/json", status=415)
	if not request.accept_mimetypes["application/json"]:
		raise McpError(protocol.INVALID_REQUEST, "Accept must allow application/json", status=406)

	payload = transport.parse_body(request)
	context.id = payload.get("id")
	params = payload.get("params", {})
	context.version = transport.request_version(request, params)
	if context.version == protocol.LATEST_VERSION:
		transport.check_headers(request, payload, params)
		transport.check_metadata(params)
	frappe.local.yz_client_info = _client_info(params)

	if "id" not in payload:
		# A notification runs no tool and gets no JSON-RPC response.
		return Response(status=202)

	context.method = payload["method"]
	result = dispatch(context.method, params, context.version)
	return transport.json_response(protocol.result_envelope(context.id, result, context.version))


def _check_principal() -> None:
	kind = access.principal()
	if kind == access.GUEST:
		# Not reachable today: Frappe refuses a guest with 403 before this code runs, because the
		# endpoint does not allow guests. The check stays as a second guard.
		raise McpError(protocol.INVALID_REQUEST, "Authentication required", status=401)
	if kind == access.OTHER:
		# API keys and OAuth tokens are long-lived and do not carry the G-148 limits.
		# The user is known here, so the denial is logged. The 403 response rolls the request
		# back, so the log row is committed first. Nothing else has been written yet.
		access.record_denial("auth", "credential_not_accepted")
		raise _logged(
			McpError(
				protocol.INVALID_REQUEST,
				"Use a session cookie or an agent token on this endpoint",
				status=403,
			)
		)


def _client_info(params: dict) -> str | None:
	meta = params.get("_meta")
	info = (meta.get(protocol.META_CLIENT) if isinstance(meta, dict) else None) or params.get("clientInfo")
	if isinstance(info, dict) and isinstance(info.get("name"), str):
		return f"{info['name']} {info.get('version', '')}".strip()[:140]
	return None


def dispatch(method: str, params: dict[str, Any], version: str) -> dict:
	if method == "initialize" and version == protocol.LEGACY_VERSION:
		if not isinstance(params.get("protocolVersion"), str) or not isinstance(
			params.get("capabilities"), dict
		):
			raise McpError(protocol.INVALID_PARAMS, "initialize requires protocolVersion and capabilities")
		return {
			"protocolVersion": protocol.LEGACY_VERSION,
			"capabilities": {"tools": {"listChanged": False}},
			**_server_configuration(),
		}
	if method == "ping":
		return {}
	if method == "server/discover" and version == protocol.LATEST_VERSION:
		return {
			"supportedVersions": list(protocol.SUPPORTED_VERSIONS),
			"capabilities": {"tools": {}},
			**_server_configuration(),
			"ttlMs": LIST_TTL_MS,
			"cacheScope": "private",
		}
	if method == "tools/list":
		return {"tools": registry.definitions(), "ttlMs": LIST_TTL_MS, "cacheScope": "private"}
	if method == "tools/call":
		return call_tool(params)
	raise McpError(METHOD_NOT_FOUND, f"Unknown MCP method: {method}", status=404)


def _server_configuration() -> dict:
	instructions = "\n".join(
		(
			f"This is the AI access layer of the site {get_host_name()}.",
			f"You act as {get_fullname()} ({frappe.session.user}) with exactly that user's permissions.",
			"Call get_doctype_schema before you read or write a DocType.",
			"Write tools never write. They open a proposal that the user approves in the panel.",
			"You cannot approve a proposal. Ask the user to approve it, then call get_proposal.",
			"If a result is unknown, do not repeat the action. Ask the user to check and resolve it.",
			"Secret fields are never returned and cannot be written through tools.",
		)
	)
	return {"serverInfo": protocol.server_info(), "instructions": instructions}


def call_tool(params: dict) -> dict:
	"""Run the tool. Every result and every denial is written to an "AI Action Log" record."""
	started = time.monotonic()
	name = params.get("name")
	# A call is spent before the tool is looked up. An unknown tool name spends one too.
	if not agent_token.spend_call():
		access.record_denial("call", "token_call_limit", tool=str(name)[:140], started=started)
		raise _logged(McpError(protocol.INVALID_REQUEST, "The agent token has no calls left", status=401))
	tool = registry.find(name) if isinstance(name, str) else None
	if tool is None:
		access.record_denial("call", "unknown_tool", tool=str(name)[:140], started=started)
		raise _logged(McpError(METHOD_NOT_FOUND, f"Unknown MCP tool: {name}", status=404))

	raw = params.get("arguments", {})
	context = {"tool": tool.name, "tool_class": tool.tool_class, "started": started}
	context.update(_target(raw if isinstance(raw, dict) else {}))

	try:
		if not tool.visible():
			raise ToolDenied(
				"role_required", _("Your roles do not allow tool {0}.", context=CONTEXT).format(tool.name)
			)
		try:
			arguments = tool.arguments.model_validate(raw).model_dump()
		except ValidationError as error:
			raise ToolDenied("invalid_arguments", validation_message(error)) from None
		context["arguments"] = arguments

		if tool.kind == "write":
			result, proposal = proposals.open_proposal(tool, arguments)
			access.record(
				"preview",
				decision="allowed",
				proposal=proposal.name,
				approval_state=proposal.status,
				**{**context, "target_doctype": proposal.target_doctype, "target_name": proposal.target_name},
			)
			return _success(result)

		result = tool.handler(**arguments)
		# A read tool cannot leave a permanent write. If it wrote, it is rolled back here.
		frappe.db.rollback()
		access.record("call", decision="allowed", **context)
		return _success(result)
	except ToolDenied as error:
		return _deny(context, error.code, str(error))
	except frappe.PermissionError as error:
		return _deny(context, "permission", str(error) or "Not permitted")
	except frappe.DoesNotExistError as error:
		return _deny(context, "not_found", str(error) or "Not found")
	except frappe.ValidationError as error:
		# A tool, most often the preview of an app tool, refused the input.
		return _deny(context, "invalid_arguments", str(error) or "Not valid")
	except McpError:
		raise
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"AI tool {tool.name} failed")
		frappe.clear_messages()
		access.record("call", decision="error", deny_reason="internal_error", **context)
		return _error("internal_error", "The tool failed. The error was recorded.")


def _target(arguments: dict) -> dict:
	doctype = arguments.get("doctype") or arguments.get("report")
	name = arguments.get("name")
	return {
		"target_doctype": doctype if isinstance(doctype, str) else None,
		"target_name": name if isinstance(name, str) else None,
	}


def _deny(context: dict, code: str, message: str) -> dict:
	"""A denial is not an error. A tool result is returned. So the log write is not rolled back."""
	frappe.db.rollback()
	frappe.clear_messages()
	stage = "preview" if context["tool_class"] in ("write", "admin") else "call"
	access.record(stage, decision="denied", deny_reason=code, **context)
	return _error(code, strip_html(message).strip())


def _success(value: Any) -> dict:
	structured = value if isinstance(value, dict) else {"result": value}
	text = json.dumps(structured, default=json_handler, allow_nan=False, ensure_ascii=False)
	return {
		"content": [{"type": "text", "text": text}],
		"structuredContent": json.loads(text),
		"isError": False,
	}


def _error(code: str, message: str) -> dict:
	structured = {"error": {"code": code, "message": message}}
	return {
		"content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
		"structuredContent": structured,
		"isError": True,
	}
