"""Small JSON HTTP client using only the Python standard library.

Each request has a timeout (G-13). The client does not follow redirects.
This prevents tokens from being sent outside the configured target.
Error messages omit response bodies, which may contain personal data.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field

_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


# Error names the service knows from the target contracts (docs/sozlesmeler.md, sections 5 and 6).
# A target's error name is free text chosen by the target. A shape check is not enough: a plain
# word may be a customer code. Only a name from this fixed list is kept. Any other value is
# dropped, so it cannot reach a log line, a stored error text or a reply.
KNOWN_ERROR_CODES = frozenset(
    {
        "IdentityNotFound",
        "IdentityConflict",
        "EmailMismatch",
        "EmailInUse",
        "EmailNotVerified",
        "InvalidInput",
        "InvalidTeamSelector",
        "ValidationError",
        "PermissionError",
    }
)
_MAX_ERROR_BYTES = 65536


class HttpError(Exception):
    """The server returned a non-2xx response.

    `code` is the target's error name (Frappe's `exc_type`), and only when it is one of
    `KNOWN_ERROR_CODES`. Every other name and the rest of the body are dropped because they may
    hold personal data. The text of the error is the HTTP status and, at most, that fixed name.
    """

    def __init__(self, status: int, code: str | None = None) -> None:
        code = code if code in KNOWN_ERROR_CODES else None
        super().__init__(f"HTTP {status} {code}" if code else f"HTTP {status}")
        self.status = status
        self.code = code
        # A caller that knows the endpoint may mark another status as worth a retry,
        # for example 409 for a lock conflict.
        self.retryable = status >= 500 or status in (408, 429)

    @property
    def transient(self) -> bool:
        return self.retryable


class UnknownOutcome(Exception):
    """The target did not confirm success. Completion is unknown.

    For example, the target queued the work and returned 202. Do not retry blindly.
    """


class TransportError(Exception):
    """The request did not reach the server, or the response could not be read."""

    transient = True


class ConnectFailed(TransportError):
    """No connection was established. The request was not sent to the server."""


@dataclass(frozen=True)
class Response:
    status: int
    body: object = None
    headers: Mapping[str, str] = field(default_factory=dict)


def _error_code(error: urllib.error.HTTPError) -> str | None:
    """Read `exc_type` from a JSON error body. Returns None when there is no usable name."""
    try:
        body = json.loads(error.read(_MAX_ERROR_BYTES).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    code = body.get("exc_type") if isinstance(body, dict) else None
    return code if isinstance(code, str) and code in KNOWN_ERROR_CODES else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def request_json(
    method: str,
    url: str,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    query: Mapping[str, object] | None = None,
    json_body: object = None,
    has_body: bool = False,
    form: Mapping[str, str] | None = None,
) -> Response:
    """Send the request and decode the JSON response.

    When `has_body` is true, send `json_body` even if its value is `None`.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError("only http and https URLs are allowed")
    if query:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})}"
    send_headers = {"Accept": "application/json", **(headers or {})}
    data: bytes | None = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        send_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif has_body or json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        send_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=send_headers)
    try:
        with _OPENER.open(request, timeout=timeout) as raw:
            payload = raw.read(_MAX_RESPONSE_BYTES + 1)
            response_headers = {name.lower(): value for name, value in raw.headers.items()}
            status = raw.status
    except urllib.error.HTTPError as error:
        code = _error_code(error)
        error.close()
        raise HttpError(error.code, code) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (ConnectionRefusedError, socket.gaierror)):
            raise ConnectFailed("connection failed") from None
        raise TransportError(type(error.reason).__name__) from None
    except (TimeoutError, ConnectionError, OSError) as error:
        # The request may have been sent. The response could not be read.
        raise TransportError(type(error).__name__) from None
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise TransportError("response too large")
    if not payload.strip():
        return Response(status=status, body=None, headers=response_headers)
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TransportError("response is not JSON") from None
    return Response(status=status, body=body, headers=response_headers)
