"""Küçük JSON HTTP istemcisi. Yalnız Python'un kendi kitaplığını kullanır.

Her isteğin süre sınırı vardır (G-13). İstemci yönlendirmeyi izlemez.
Böylece belirteç ayardaki hedefin dışına gitmez.
Hata metni yanıt gövdesini taşımaz. Gövde kişisel veri içerebilir.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field

_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class HttpError(Exception):
    """Sunucu 2xx dışında yanıt verdi."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status

    @property
    def transient(self) -> bool:
        return self.status >= 500 or self.status in (408, 429)


class TransportError(Exception):
    """İstek sunucuya ulaşmadı ya da yanıt okunamadı."""

    transient = True


@dataclass(frozen=True)
class Response:
    status: int
    body: object = None
    headers: Mapping[str, str] = field(default_factory=dict)


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
    """İsteği gönderir ve JSON yanıtı çözer.

    `has_body` doğruysa `json_body` değeri `None` olsa bile gövde olarak gider.
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
        error.close()
        raise HttpError(error.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
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
