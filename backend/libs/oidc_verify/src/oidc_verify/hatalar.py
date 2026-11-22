"""Hata türü. `code` alanı nedeni söyler."""

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
    """Geçersiz belirteç. `code` sözleşmedeki kodlardan biridir."""

    def __init__(self, code: str, message: str | None = None):
        if code not in KODLAR:
            raise ValueError(f"Bilinmeyen hata kodu: {code}")
        self.code = code
        super().__init__(message or code)
