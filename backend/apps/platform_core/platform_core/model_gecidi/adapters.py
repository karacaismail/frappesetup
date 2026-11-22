"""Translate the gateway's text and function calls to provider HTTP formats."""

import json
import logging
import re
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from socket import SHUT_RDWR
from threading import Timer
from time import monotonic
from urllib.parse import quote, quote_plus, urlsplit

import requests
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import HTTPError, MaxRetryError, NewConnectionError, ReadTimeoutError

LOGGER = logging.getLogger(__name__)
_RESPONSE_DEADLINE = ContextVar("model_response_deadline", default=None)
CALL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
POTENTIALLY_BILLED = {"timeout", "upstream", "invalid_response"}
PATHS = {
	"openai": "/v1/chat/completions",
	"anthropic": "/v1/messages",
	"gemini": "/v1beta/models/{model}:generateContent",
	"ollama": "/api/chat",
}


@dataclass(frozen=True)
class Endpoint:
	api: str
	adapter: str
	base_url: str = field(repr=False)
	auth: str = "none"
	secret: str = field(default="", repr=False)
	token_url: str = field(default="", repr=False)
	client_id: str = field(default="", repr=False)


class GatewayError(Exception):
	def __init__(self, code, *, may_be_billed=None):
		super().__init__(code)
		self.code = code
		self.may_be_billed = code in POTENTIALLY_BILLED if may_be_billed is None else may_be_billed


@contextmanager
def _interrupt_socket(socket, deadline):
	"""Interrupt a blocking HTTP parser at a wall-clock deadline."""
	remaining = deadline - monotonic()
	if remaining <= 0:
		raise GatewayError("timeout")
	if socket is None:
		yield
		return

	def interrupt():
		# Shutdown wakes a blocked socket reader. Closing its buffered file
		# from here could instead wait for the read to release its buffer lock.
		with suppress(OSError):
			socket.shutdown(SHUT_RDWR)

	timer = Timer(remaining, interrupt)
	timer.daemon = True
	timer.start()
	try:
		yield
	except Exception:
		if monotonic() >= deadline:
			raise GatewayError("timeout") from None
		raise
	else:
		if monotonic() >= deadline:
			raise GatewayError("timeout")
	finally:
		timer.cancel()
		timer.join()


class _ResponseDeadline:
	def getresponse(self):
		deadline = _RESPONSE_DEADLINE.get()
		if deadline is None:
			return super().getresponse()
		with _interrupt_socket(self.sock, deadline):
			return super().getresponse()


class _ProviderHTTPConnection(_ResponseDeadline, HTTPConnection):
	pass


class _ProviderHTTPSConnection(_ResponseDeadline, HTTPSConnection):
	pass


class _ProviderHTTPPool(HTTPConnectionPool):
	ConnectionCls = _ProviderHTTPConnection


class _ProviderHTTPSPool(HTTPSConnectionPool):
	ConnectionCls = _ProviderHTTPSConnection


class _ProviderAdapter(requests.adapters.HTTPAdapter):
	def init_poolmanager(self, *args, **kwargs):
		super().init_poolmanager(*args, **kwargs)
		self.poolmanager.pool_classes_by_scheme = {"http": _ProviderHTTPPool, "https": _ProviderHTTPSPool}


class _ProviderSession(requests.Session):
	def __init__(self):
		super().__init__()
		self.mount("http://", _ProviderAdapter())
		self.mount("https://", _ProviderAdapter())

	def get_redirect_target(self, response):
		# Requests otherwise drains redirect bodies even with allow_redirects=False.
		return None


def _url(value, *, secure):
	parsed = urlsplit(value)
	if (
		parsed.scheme not in ({"https"} if secure else {"http", "https"})
		or not parsed.hostname
		or parsed.username is not None
		or parsed.query
		or parsed.fragment
	):
		raise GatewayError("configuration")
	return value


def _read_body(response, deadline, max_bytes):
	# urllib3's read1 returns after one socket read. Apply the remaining wall time
	# to the underlying CPython socket as well, so a final quiet read cannot
	# spend the original read timeout again. A fully read response has no socket.
	if response.headers.get("Content-Encoding", "identity").strip().lower() != "identity":
		raise GatewayError("invalid_response")
	raw = response.raw
	buffered = getattr(getattr(raw, "_fp", None), "fp", None)
	socket = getattr(getattr(buffered, "raw", None), "_sock", None)
	body = bytearray()
	with _interrupt_socket(socket, deadline):
		while chunk := raw.read1(8192, decode_content=False):
			body.extend(chunk)
			if len(body) > max_bytes:
				raise GatewayError("invalid_response")
	try:
		return json.loads(body)
	except (ValueError, RecursionError):
		raise GatewayError("invalid_response") from None


def _post_json(session, url, *, timeout, connect_timeout, deadline, max_bytes, before_post, **kwargs):
	if before_post is not None and not before_post():
		raise GatewayError("reservation_lost")
	remaining = deadline - monotonic()
	if remaining <= 0:
		raise GatewayError("not_sent")
	# Keep both socket timeouts inside the shared route budget.
	connect = min(connect_timeout, remaining / 2)
	read = min(timeout, remaining - connect)
	response_deadline = _RESPONSE_DEADLINE.set(deadline)
	try:
		with session.post(
			url, timeout=(connect, read), allow_redirects=False, stream=True, **kwargs
		) as response:
			if response.status_code != 200:
				return response.status_code, None
			return response.status_code, _read_body(response, min(deadline, monotonic() + read), max_bytes)
	except requests.ConnectTimeout:
		raise GatewayError("connect_failed") from None
	except (requests.Timeout, ReadTimeoutError, TimeoutError):
		raise GatewayError("timeout") from None
	except requests.ConnectionError as failure:
		reason = failure.args[0] if failure.args else None
		if isinstance(reason, MaxRetryError) and isinstance(reason.reason, NewConnectionError):
			raise GatewayError("connect_failed") from None
		raise GatewayError("upstream") from None
	except (requests.exceptions.InvalidURL, requests.exceptions.InvalidHeader):
		raise GatewayError("configuration") from None
	except (requests.RequestException, HTTPError):
		raise GatewayError("upstream") from None
	except GatewayError:
		raise
	except Exception:
		# Once post has started, an unexpected transport failure may follow
		# a provider charge. Never expose the raw transport exception.
		raise GatewayError("invalid_response") from None
	finally:
		_RESPONSE_DEADLINE.reset(response_deadline)


def _contains_secret(value, secrets):
	if isinstance(value, str):
		return any(secret and secret in value for secret in secrets)
	if isinstance(value, dict):
		return any(_contains_secret(item, secrets) for item in (*value, *value.values()))
	if isinstance(value, list):
		return any(_contains_secret(item, secrets) for item in value)
	return False


def _headers(endpoint, session, timeout, connect_timeout, deadline, *, allow_test_http, before_post):
	headers = {}
	if endpoint.adapter == "anthropic":
		headers["anthropic-version"] = "2023-06-01"
	if endpoint.auth == "api_key":
		if endpoint.adapter == "anthropic":
			headers["x-api-key"] = endpoint.secret
		elif endpoint.adapter == "gemini":
			headers["x-goog-api-key"] = endpoint.secret
		else:
			headers["Authorization"] = f"Bearer {endpoint.secret}"
	elif endpoint.auth == "bearer":
		headers["Authorization"] = f"Bearer {endpoint.secret}"
	elif endpoint.auth == "oauth_client_credentials":
		if not endpoint.client_id or not endpoint.secret:
			raise GatewayError("configuration")
		status, token_body = _post_json(
			session,
			_url(endpoint.token_url, secure=not allow_test_http),
			data={"grant_type": "client_credentials"},
			auth=(quote_plus(endpoint.client_id), quote_plus(endpoint.secret)),
			timeout=timeout,
			connect_timeout=connect_timeout,
			deadline=deadline,
			max_bytes=65536,
			before_post=before_post,
		)
		if status != 200:
			raise GatewayError(_status_code(status), may_be_billed=False)
		token = token_body.get("access_token") if isinstance(token_body, dict) else None
		if not isinstance(token, str) or not token:
			raise GatewayError("invalid_response")
		headers["Authorization"] = f"Bearer {token}"
	elif endpoint.auth != "none":
		raise GatewayError("configuration")
	return headers


def _function_tools(tools):
	return [{"type": "function", "function": tool} for tool in tools]


def _payload(adapter, model, messages, limit, tools, schema):
	if adapter == "openai":
		payload = {"model": model, "messages": messages, "max_completion_tokens": limit}
		if tools:
			payload["tools"] = _function_tools(tools)
		if schema is not None:
			payload["response_format"] = {
				"type": "json_schema",
				"json_schema": {"name": "response", "schema": schema},
			}
		return payload
	if adapter == "ollama":
		payload = {"model": model, "messages": messages, "stream": False, "options": {"num_predict": limit}}
		if tools:
			payload["tools"] = _function_tools(tools)
		if schema is not None:
			payload["format"] = schema
		return payload

	system = "\n\n".join(message["content"] for message in messages if message["role"] == "system")
	dialogue = [message for message in messages if message["role"] != "system"]
	if adapter == "anthropic":
		payload = {"model": model, "messages": dialogue, "max_tokens": limit}
		if system:
			payload["system"] = system
		if tools:
			payload["tools"] = [
				{
					"name": tool["name"],
					"description": tool.get("description", ""),
					"input_schema": tool["parameters"],
				}
				for tool in tools
			]
		if schema is not None:
			payload["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
		return payload

	config = {"maxOutputTokens": limit}
	payload = {
		"contents": [
			{
				"role": "model" if message["role"] == "assistant" else "user",
				"parts": [{"text": message["content"]}],
			}
			for message in dialogue
		],
		"generationConfig": config,
	}
	if system:
		payload["systemInstruction"] = {"parts": [{"text": system}]}
	if tools:
		payload["tools"] = [{"functionDeclarations": tools}]
	if schema is not None:
		config.update(responseMimeType="application/json", responseJsonSchema=schema)
	return payload


def _call(name, arguments, identifier):
	if isinstance(arguments, str):
		arguments = json.loads(arguments)
	if (
		not isinstance(arguments, dict)
		or not isinstance(name, str)
		or not isinstance(identifier, str)
		or not CALL_ID.fullmatch(identifier)
	):
		raise ValueError("Invalid function call")
	return {"id": identifier, "name": name, "arguments": arguments}


def _call_id(call, index):
	identifier = call.get("id")
	return f"call-{index}" if identifier is None else identifier


def _normalize(adapter, body):
	if adapter in {"openai", "ollama"}:
		message = body["choices"][0]["message"] if adapter == "openai" else body["message"]
		if message.get("refusal"):
			raise GatewayError("rejected", may_be_billed=True)
		calls = [
			_call(call["function"]["name"], call["function"]["arguments"], _call_id(call, index))
			for index, call in enumerate(message.get("tool_calls", []))
		]
		if adapter == "openai":
			usage = body.get("usage") or {}
			return (
				message.get("content") or "",
				calls,
				usage.get("prompt_tokens"),
				usage.get("completion_tokens"),
			)
		return message.get("content") or "", calls, body.get("prompt_eval_count"), body.get("eval_count")
	if adapter == "anthropic":
		if body.get("stop_reason") == "refusal":
			raise GatewayError("rejected", may_be_billed=True)
		parts = body["content"]
		text = "".join(part["text"] for part in parts if part["type"] == "text")
		calls = [
			_call(part["name"], part["input"], part["id"]) for part in parts if part["type"] == "tool_use"
		]
		usage = body.get("usage") or {}
		return text, calls, usage.get("input_tokens"), usage.get("output_tokens")

	candidate = body["candidates"][0]
	if candidate.get("finishReason") not in {None, "STOP", "MAX_TOKENS"}:
		raise GatewayError("rejected", may_be_billed=True)
	parts = candidate["content"]["parts"]
	text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
	calls = [
		_call(call["name"], call.get("args", {}), _call_id(call, index))
		for index, call in enumerate(part["functionCall"] for part in parts if "functionCall" in part)
	]
	usage = body.get("usageMetadata") or {}
	output = usage.get("candidatesTokenCount")
	thoughts = usage.get("thoughtsTokenCount")
	if thoughts is not None:
		output = (output or 0) + thoughts
	return text, calls, usage.get("promptTokenCount"), output


def _status_code(status):
	if 200 <= status < 300:
		return "invalid_response"
	if status == 401:
		return "authentication"
	if status == 403:
		return "forbidden"
	if status == 408:
		return "timeout"
	if status == 429:
		return "rate_limit"
	if 500 <= status < 600:
		return "upstream"
	return "rejected"


def complete(
	endpoint,
	model,
	messages,
	limit,
	*,
	tools=(),
	schema=None,
	timeout=30,
	connect_timeout=5,
	deadline=None,
	allow_test_http=False,
	before_post=None,
):
	"""Make one synchronous attempt. Exceptions and logs carry only fixed codes."""
	error = GatewayError("configuration")
	if deadline is None:
		deadline = monotonic() + connect_timeout + timeout
	try:
		base = _url(
			endpoint.base_url,
			secure=not (allow_test_http or (endpoint.adapter == "ollama" and endpoint.auth == "none")),
		)
		if endpoint.auth in {"api_key", "bearer"} and not endpoint.secret:
			raise error
		path = PATHS[endpoint.adapter].format(model=quote(model, safe=""))
		payload = _payload(endpoint.adapter, model, messages, limit, tools, schema)
		with _ProviderSession() as session:
			session.trust_env = False
			session.headers["Accept-Encoding"] = "identity"
			try:
				headers = _headers(
					endpoint,
					session,
					timeout,
					connect_timeout,
					deadline,
					allow_test_http=allow_test_http,
					before_post=before_post,
				)
			except GatewayError as failure:
				# Token issuance cannot have sent a model request.
				raise GatewayError(failure.code, may_be_billed=False) from None
			error = GatewayError("invalid_response")
			status, body = _post_json(
				session,
				base.rstrip("/") + path,
				headers=headers,
				json=payload,
				timeout=timeout,
				connect_timeout=connect_timeout,
				deadline=deadline,
				max_bytes=2 * 1024 * 1024,
				before_post=before_post,
			)
		if status != 200:
			raise GatewayError(_status_code(status))
		if body.get("error") or body.get("promptFeedback", {}).get("blockReason"):
			raise GatewayError("rejected", may_be_billed=True)
		text, calls, input_tokens, output_tokens = _normalize(endpoint.adapter, body)
		if not isinstance(text, str) or any(
			count is not None and (type(count) is not int or count < 0)
			for count in (input_tokens, output_tokens)
		):
			raise error
		allowed_names = {tool["name"] for tool in tools}
		if any(call["name"] not in allowed_names for call in calls) or len(
			{call["id"] for call in calls}
		) != len(calls):
			raise error
		bearer = headers.get("Authorization", "").removeprefix("Bearer ")
		if _contains_secret([text, calls], (endpoint.secret, bearer)):
			raise GatewayError("invalid_response")
		return {
			"api": endpoint.api,
			"model": model,
			"text": text,
			"tool_calls": calls,
			"usage": {"input": input_tokens, "output": output_tokens},
		}
	except GatewayError as failure:
		error = failure
	except Exception:
		# Preserve the dispatch phase without exposing provider data.
		pass
	LOGGER.warning("Model gateway attempt failed: %s", error.code)
	raise GatewayError(error.code, may_be_billed=error.may_be_billed)
