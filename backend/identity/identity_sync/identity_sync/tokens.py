"""Keycloak'tan istemci kimlik bilgisiyle servis belirteci alır.

Her hedef için ayrı belirteç istenir. Belirteç yalnız o hedefin `aud` değerini taşır
(`docs/sozlesmeler.md`, 2. bölüm). Belirteç bellekte durur. Diske ve günlüğe yazılmaz.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping

from identity_sync.httpjson import TransportError, request_json

_EXPIRY_MARGIN_SECONDS = 30.0


class TokenProvider:
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        *,
        timeout: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._clock = clock
        self._cache: dict[str, tuple[str, float]] = {}

    def get(self, scope: str) -> str:
        """`scope` kapsamı için geçerli bir erişim belirteci döner."""
        cached = self._cache.get(scope)
        if cached and cached[1] > self._clock():
            return cached[0]
        form = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if scope:
            form["scope"] = scope
        body = request_json("POST", self._token_url, timeout=self._timeout, form=form).body
        if not isinstance(body, Mapping) or not isinstance(body.get("access_token"), str):
            raise TransportError("token response has no access_token")
        expires_in = body.get("expires_in")
        lifetime = float(expires_in) if isinstance(expires_in, (int, float)) else 0.0
        self._cache[scope] = (body["access_token"], self._clock() + lifetime - _EXPIRY_MARGIN_SECONDS)
        return body["access_token"]
