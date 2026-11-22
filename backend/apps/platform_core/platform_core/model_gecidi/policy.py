"""Validate model input and apply the tenant's outbound data policy."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit

import frappe

from platform_core.model_gecidi import agent_access

MAX_BYTES = 256 * 1024
MAX_OUTPUT = 16_384
MANAGERS = {"AI Manager", "System Manager"}
ROLES = {"user", "assistant", "system"}
TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
SENSITIVE = re.compile(
	r"(?i)\b(?:TR(?:[ -]?\d){24}|\d(?:[ -]?\d){12,18}|\d{10,11})\b"
	r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}"
	r"|(?<!\w)\+?90(?:[ .-]?\d){10}(?!\w)"
)


class Denied(Exception):
	def __init__(self, status, code):
		super().__init__(code)
		self.status = status
		self.code = code


@dataclass(frozen=True)
class Request:
	messages: list
	tools: list
	schema: dict | None
	limit: int

	def masked(self):
		return Request(
			[{**item, "content": SENSITIVE.sub("[REDACTED]", item["content"])} for item in self.messages],
			self.tools,
			self.schema,
			self.limit,
		)


def parse(messages, tools, schema, limit):
	tools = [] if tools is None else tools
	if not (
		type(limit) is int
		and 1 <= limit <= MAX_OUTPUT
		and isinstance(messages, list)
		and 1 <= len(messages) <= 128
		and isinstance(tools, list)
		and len(tools) <= 12
		and (schema is None or isinstance(schema, dict))
	):
		raise Denied(400, "invalid_request")
	for message in messages:
		if (
			not isinstance(message, dict)
			or set(message) != {"role", "content"}
			or not isinstance(message["role"], str)
			or message["role"] not in ROLES
			or not isinstance(message["content"], str)
		):
			raise Denied(400, "invalid_request")
	for tool in tools:
		if (
			not isinstance(tool, dict)
			or set(tool) - {"name", "description", "parameters"}
			or not isinstance(tool.get("name"), str)
			or not TOOL_NAME.fullmatch(tool["name"])
			or not isinstance(tool.get("description", ""), str)
			or not isinstance(tool.get("parameters"), dict)
		):
			raise Denied(400, "invalid_request")
	try:
		body = json.dumps([messages, tools, schema], allow_nan=False, ensure_ascii=False).encode()
	except (TypeError, ValueError, RecursionError):
		raise Denied(400, "invalid_request") from None
	if len(body) > MAX_BYTES:
		raise Denied(400, "invalid_request")
	return Request(messages, tools, schema, limit)


def require_session(*, managers_only=False):
	"""Allow human sessions and, for completion, the shared gateway-scoped agent identity."""
	if frappe.session.user in ("", "Guest"):
		raise Denied(401, "authentication_required")
	if managers_only and (agent_access.is_agent() or MANAGERS.isdisjoint(frappe.get_roles())):
		raise Denied(403, "permission_denied")
	if not agent_access.is_agent():
		sid = frappe.request.cookies.get("sid")
		if not sid or sid != frappe.session.sid or frappe.get_request_header("Authorization"):
			raise Denied(401, "authentication_required")


def require_route(route):
	roles = set(frappe.get_roles())
	if not route.enabled or (MANAGERS.isdisjoint(roles) and route.required_role not in roles):
		raise Denied(403, "permission_denied")


def payload_digest(request):
	"""Hash the complete canonical payload that would leave the site."""
	body = json.dumps(
		[request.messages, request.tools, request.schema, request.limit],
		sort_keys=True,
		separators=(",", ":"),
		ensure_ascii=False,
	)
	return sha256(body.encode()).hexdigest()


def outbound(base, oauth_url, route, request):
	"""Use deployment-approved destinations and payloads for network dispatch."""
	endpoints = frappe.conf.get("model_gateway_endpoints") or {}
	kind = endpoints.get(base)
	if kind not in {"local", "external"} or (oauth_url and endpoints.get(oauth_url) != kind):
		raise Denied(503, "endpoint_unavailable")
	if kind == "local":
		return request
	if urlsplit(base).scheme != "https" or (oauth_url and urlsplit(oauth_url).scheme != "https"):
		raise Denied(503, "endpoint_unavailable")
	if route is None:
		# The connection check sends only the server's fixed public probe.
		return request
	if route.data_policy != "masked":
		raise Denied(403, "data_policy_denied")
	# Changing tool or schema identifiers can change the contract. Refuse
	# matching sensitive metadata instead of silently rewriting it.
	if SENSITIVE.search(json.dumps([request.tools, request.schema], ensure_ascii=False)):
		raise Denied(403, "data_policy_denied")
	masked = request.masked()
	approved = (frappe.conf.get("model_gateway_external_payloads") or {}).get(route.name, [])
	if not isinstance(approved, list) or payload_digest(masked) not in approved:
		raise Denied(403, "data_policy_denied")
	return masked
