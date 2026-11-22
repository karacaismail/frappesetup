"""MCP ucu: Streamable HTTP, tek JSON yanıt, oturumsuz.

Protokol ayrıştırması Frappe'nin `frappe.mcp.transport` ve `frappe.mcp.protocol`
modüllerinden gelir. Araçlar, kimlik kuralları ve günlük bu katmanındır.
Karar: docs/kararlar/0002-yapay-zeka-katmani.md.
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
from platform_core.yapay_zeka.errors import ToolDenied

LIST_TTL_MS = 60000


def handle() -> Response:
	"""Hatalar `frappe.app` içine çıkar. Orası işlemi geri alır ve MCP zarfıyla yanıtlar."""
	request = frappe.request
	context = frappe.local.mcp_request = transport.RequestContext()
	transport.check_origin(request)
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
		# Bildirim araç çalıştırmaz ve JSON-RPC yanıtı almaz.
		return Response(status=202)

	context.method = payload["method"]
	result = dispatch(context.method, params, context.version)
	return transport.json_response(protocol.result_envelope(context.id, result, context.version))


def _check_principal() -> None:
	kind = access.principal()
	if kind == access.GUEST:
		raise McpError(protocol.INVALID_REQUEST, "Authentication required", status=401)
	if kind == access.OTHER:
		# API anahtarı ve OAuth belirteci uzun ömürlüdür ve G-148 sınırlarını taşımaz.
		raise McpError(
			protocol.INVALID_REQUEST, "Use a session cookie or an agent token on this endpoint", status=403
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
	"""Aracı çalıştırır. Her sonuç ve her ret “AI Action Log” kaydına yazılır."""
	started = time.monotonic()
	name = params.get("name")
	# Çağrı hakkı araç aranmadan önce düşer. Bilinmeyen araç adı da hak harcar.
	if not agent_token.spend_call():
		access.record(
			"call", decision="denied", deny_reason="token_call_limit", tool=str(name)[:140], started=started
		)
		# 401 yanıtı işlemi geri alır. Ret kaydı için burada kesinleştirilir.
		frappe.db.commit()  # nosemgrep
		raise McpError(protocol.INVALID_REQUEST, "The agent token has no calls left", status=401)
	tool = registry.find(name) if isinstance(name, str) else None
	if tool is None:
		access.record(
			"call", decision="denied", deny_reason="unknown_tool", tool=str(name)[:140], started=started
		)
		# 404 yanıtı işlemi geri alır. Ret kaydı için burada kesinleştirilir.
		frappe.db.commit()  # nosemgrep
		raise McpError(METHOD_NOT_FOUND, f"Unknown MCP tool: {name}", status=404)

	raw = params.get("arguments", {})
	context = {"tool": tool.name, "tool_class": tool.tool_class, "started": started}
	context.update(_target(raw if isinstance(raw, dict) else {}))

	try:
		if not tool.visible():
			raise ToolDenied("role_required", _("Your roles do not allow tool {0}.").format(tool.name))
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
		# Okuma aracı kalıcı yazı bırakamaz. Yazdıysa burada geri alınır.
		frappe.db.rollback()
		access.record("call", decision="allowed", **context)
		return _success(result)
	except ToolDenied as error:
		return _deny(context, error.code, str(error))
	except frappe.PermissionError as error:
		return _deny(context, "permission", str(error) or "Not permitted")
	except frappe.DoesNotExistError as error:
		return _deny(context, "not_found", str(error) or "Not found")
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
	"""Ret hata değildir. Araç sonucu döner. Böylece günlük yazısı geri alınmaz."""
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
