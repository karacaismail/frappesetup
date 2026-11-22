"""Validate model input and apply the tenant's outbound data policy."""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import frappe

MAX_BYTES = 256 * 1024
MAX_OUTPUT = 16_384
MANAGERS = {"PLT AI Manager", "System Manager"}
ROLES = {"user", "assistant", "system"}
TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
SENSITIVE = re.compile(
	r"(?i)(?<![\w])(?:TR(?:[ -]?[0-9]){24}|"
	r"(?:\+90[ .-]?|0[ .-]?)?\(?[2-5][0-9]{2}\)?(?:[ .-]?[0-9]){7}|"
	r"[0-9](?:[ -]?[0-9]){9,10})(?![\w]|[ -][0-9])"
	r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}"
)
CARD = re.compile(r"(?<![\w])(?:[0-9][ -]?){12,18}[0-9](?![\w]|[ -][0-9])")


def _mask_card(match):
	digits = [int(char) for char in match.group() if char.isdigit()]
	checksum = sum(
		(value * 2 - 9 if value > 4 else value * 2) if index % 2 else value
		for index, value in enumerate(reversed(digits))
	)
	return "[REDACTED]" if checksum % 10 == 0 else match.group()


def _mask(text):
	return SENSITIVE.sub("[REDACTED]", CARD.sub(_mask_card, text))


def _mask_metadata(value):
	if isinstance(value, dict):
		if any(not isinstance(key, str) or _mask(key) != key for key in value):
			raise Denied(403, "data_policy_denied")
		return {key: _mask_metadata(item) for key, item in value.items()}
	if isinstance(value, list):
		return [_mask_metadata(item) for item in value]
	if isinstance(value, str):
		return _mask(value)
	if type(value) is int and _mask(str(value)) != str(value):
		raise Denied(403, "data_policy_denied")
	return value


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
			[{**item, "content": _mask(item["content"])} for item in self.messages],
			_mask_metadata(self.tools),
			_mask_metadata(self.schema),
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


def require_user(*, managers_only=False):
	user = frappe.session.user
	if user in (None, "", "Guest") or not frappe.db.get_value("User", user, "enabled"):
		raise Denied(401, "authentication_required")
	if managers_only and MANAGERS.isdisjoint(frappe.get_roles()):
		raise frappe.PermissionError


def require_session(*, allow_api_key=False):
	"""Require a real cookie session at the HTTP boundary."""
	require_user()
	request = getattr(frappe.local, "request", None)
	sid = request.cookies.get("sid") if request is not None else None
	auth = frappe.get_request_header("Authorization") or ""
	if sid and sid != "Guest" and sid == frappe.session.sid and not auth:
		return
	if (
		allow_api_key
		and sid in (None, "", "Guest")
		and auth.partition(" ")[0].lower() in {"token", "basic"}
		and frappe.session.sid == frappe.session.user
		and not frappe.get_request_header("Frappe-Authorization-Source")
	):
		return
	raise Denied(401, "authentication_required")


def require_route(route):
	roles = set(frappe.get_roles())
	if not route.enabled or (MANAGERS.isdisjoint(roles) and route.required_role not in roles):
		raise frappe.PermissionError


def connection_policy(base, oauth_url):
	"""Return the connection kind and the separate model and OAuth IP pins."""
	endpoints = frappe.conf.get("model_gateway_endpoints") or {}
	if not isinstance(endpoints, dict):
		raise Denied(503, "endpoint_unavailable")

	def entry(url):
		if not isinstance(url, str):
			raise Denied(503, "endpoint_unavailable")
		try:
			scheme = urlsplit(url).scheme
		except ValueError:
			raise Denied(503, "endpoint_unavailable") from None
		setting = endpoints.get(url)
		if setting == "external" or (isinstance(setting, dict) and setting.get("kind") == "external"):
			if scheme == "https":
				return "external", ()
		elif isinstance(setting, dict) and setting.get("kind") == "local":
			addresses = setting.get("addresses")
			if (
				isinstance(addresses, list)
				and addresses
				and all(isinstance(address, str) for address in addresses)
				and scheme in {"http", "https"}
			):
				return "local", tuple(addresses)
		raise Denied(503, "endpoint_unavailable")

	kind, addresses = entry(base)
	if not oauth_url:
		return kind, addresses, ()
	oauth_kind, oauth_addresses = entry(oauth_url)
	if oauth_kind != kind:
		raise Denied(503, "endpoint_unavailable")
	return kind, addresses, oauth_addresses


def outbound(base, oauth_url, route, request):
	"""Use deployment-approved destinations and mask all external requests."""
	kind = connection_policy(base, oauth_url)[0]
	if kind == "local":
		return request
	if route is not None and route.data_policy != "masked":
		raise Denied(403, "data_policy_denied")
	return request.masked()
