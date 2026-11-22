"""Translate the gateway's text and function calls to provider HTTP formats."""

from dataclasses import dataclass, field
import json
import logging
from urllib.parse import quote, urlsplit

import requests


LOGGER = logging.getLogger(__name__)
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
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _url(value, *, secure):
    parsed = urlsplit(value)
    if (parsed.scheme not in ({"https"} if secure else {"http", "https"})
            or not parsed.hostname or parsed.username is not None
            or parsed.query or parsed.fragment):
        raise GatewayError("configuration")
    return value


def _headers(endpoint, session, timeout, *, allow_test_http):
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
        token_response = session.post(
            _url(endpoint.token_url, secure=not allow_test_http),
            data={"grant_type": "client_credentials"},
            auth=(endpoint.client_id, endpoint.secret), timeout=timeout, allow_redirects=False,
        )
        if token_response.status_code != 200:
            code = _status_code(token_response.status_code)
            raise GatewayError("authentication" if code == "rejected" else code)
        token = token_response.json().get("access_token")
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
                "type": "json_schema", "json_schema": {"name": "response", "schema": schema},
            }
        return payload
    if adapter == "ollama":
        payload = {"model": model, "messages": messages, "stream": False,
                   "options": {"num_predict": limit}}
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
                {"name": tool["name"], "description": tool.get("description", ""),
                 "input_schema": tool["parameters"]} for tool in tools
            ]
        if schema is not None:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        return payload

    config = {"maxOutputTokens": limit}
    payload = {
        "contents": [
            {"role": "model" if message["role"] == "assistant" else "user",
             "parts": [{"text": message["content"]}]} for message in dialogue
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
    if not isinstance(arguments, dict) or not isinstance(name, str):
        raise ValueError("Invalid function call")
    return {"id": identifier, "name": name, "arguments": arguments}


def _normalize(adapter, body):
    if adapter in {"openai", "ollama"}:
        message = body["choices"][0]["message"] if adapter == "openai" else body["message"]
        if message.get("refusal"):
            raise GatewayError("rejected")
        calls = [
            _call(call["function"]["name"], call["function"]["arguments"],
                  call.get("id") or f"call-{index}")
            for index, call in enumerate(message.get("tool_calls", []))
        ]
        if adapter == "openai":
            usage = body.get("usage") or {}
            return message.get("content") or "", calls, usage.get("prompt_tokens"), usage.get("completion_tokens")
        return message.get("content") or "", calls, body.get("prompt_eval_count"), body.get("eval_count")
    if adapter == "anthropic":
        if body.get("stop_reason") == "refusal":
            raise GatewayError("rejected")
        parts = body["content"]
        text = "".join(part["text"] for part in parts if part["type"] == "text")
        calls = [_call(part["name"], part["input"], part["id"])
                 for part in parts if part["type"] == "tool_use"]
        usage = body.get("usage") or {}
        return text, calls, usage.get("input_tokens"), usage.get("output_tokens")

    candidate = body["candidates"][0]
    if candidate.get("finishReason") not in {None, "STOP", "MAX_TOKENS"}:
        raise GatewayError("rejected")
    parts = candidate["content"]["parts"]
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    calls = [
        _call(call["name"], call.get("args", {}), call.get("id") or f"call-{index}")
        for index, call in enumerate(part["functionCall"] for part in parts if "functionCall" in part)
    ]
    usage = body.get("usageMetadata") or {}
    output = usage.get("candidatesTokenCount")
    thoughts = usage.get("thoughtsTokenCount")
    if thoughts is not None:
        output = (output or 0) + thoughts
    return text, calls, usage.get("promptTokenCount"), output


def _status_code(status):
    if status in {401, 403}:
        return "authentication"
    if status == 429:
        return "rate_limit"
    if 500 <= status < 600:
        return "upstream"
    return "rejected"


def complete(endpoint, model, messages, limit, *, tools=(), schema=None, timeout=30,
             allow_test_http=False):
    """Make one synchronous attempt. Exceptions and logs carry only fixed codes."""
    error = "configuration"
    try:
        base = _url(endpoint.base_url, secure=not (
            allow_test_http or (endpoint.adapter == "ollama" and endpoint.auth == "none")
        ))
        if endpoint.auth in {"api_key", "bearer"} and not endpoint.secret:
            raise GatewayError(error)
        path = PATHS[endpoint.adapter].format(model=quote(model, safe=""))
        payload = _payload(endpoint.adapter, model, messages, limit, tools, schema)
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                base.rstrip("/") + path,
                headers=_headers(endpoint, session, timeout, allow_test_http=allow_test_http),
                json=payload, timeout=timeout, allow_redirects=False,
            )
        if response.status_code != 200:
            raise GatewayError(_status_code(response.status_code))
        error = "invalid_response"
        body = response.json()
        if body.get("error") or body.get("promptFeedback", {}).get("blockReason"):
            raise GatewayError("rejected")
        text, calls, input_tokens, output_tokens = _normalize(endpoint.adapter, body)
        if not isinstance(text, str) or any(
            count is not None and (type(count) is not int or count < 0)
            for count in (input_tokens, output_tokens)
        ):
            raise GatewayError(error)
        return {"api": endpoint.api, "model": model, "text": text, "tool_calls": calls,
                "usage": {"input": input_tokens, "output": output_tokens}}
    except requests.Timeout:
        error = "timeout"
    except requests.exceptions.JSONDecodeError:
        error = "invalid_response"
    except requests.ConnectionError:
        error = "upstream"
    except requests.RequestException:
        error = "rejected"
    except GatewayError as failure:
        error = failure.code
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        pass
    LOGGER.warning("Model gateway attempt failed: %s", error)
    raise GatewayError(error)
