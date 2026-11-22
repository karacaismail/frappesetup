"""Error types. `TokenError.code` identifies the cause."""

from __future__ import annotations

KODLAR = frozenset(
    {
        "malformed",
        "invalid_signature",
        "unknown_kid",
        "wrong_issuer",
        "wrong_audience",
        "wrong_azp",
        "expired",
        "not_yet_valid",
        "wrong_nonce",
        "not_logout_token",
    }
)


class TokenError(Exception):
    """Invalid token. `code` is one of the error codes defined by the contract."""

    def __init__(self, code: str, message: str | None = None):
        if code not in KODLAR:
            raise ValueError(f"Unknown error code: {code}")
        self.code = code
        super().__init__(message or code)


class JwksUnavailable(Exception):
    """The key set could not be fetched and the cache has no usable keys.

    Token validity remains unknown. The calling endpoint returns an error such as HTTP 503.
    """
