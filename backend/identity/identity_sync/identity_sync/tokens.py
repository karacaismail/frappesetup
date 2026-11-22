"""Obtain service tokens from Keycloak using client credentials.

Request a separate token for each target. The token contains only that target's `aud` value
(`docs/sozlesmeler.md`, section 2). Keep tokens in memory, never on disk or in logs.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import TypeVar

from identity_sync.httpjson import HttpError, TransportError, request_json

T = TypeVar("T")

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

    def with_token(self, scope: str, call: Callable[[str], T]) -> T:
        """Call with a token. If the target returns 401, refresh the token and retry once."""
        try:
            return call(self.get(scope))
        except HttpError as error:
            if error.status != 401:
                raise
        self._cache.pop(scope, None)
        return call(self.get(scope))

    def get(self, scope: str) -> str:
        """Return a valid access token for `scope`."""
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
