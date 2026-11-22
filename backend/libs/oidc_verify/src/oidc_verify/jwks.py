"""Anahtar listesi önbelleği.

Liste `ttl_seconds` süresince saklanır. Bilinmeyen `kid` gelince liste bir kez yenilenir.
Art arda gelen bilinmeyen `kid` istekleri listeyi en çok `min_refresh_seconds` aralığıyla yeniletir.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

import jwt

from oidc_verify.hatalar import TokenError

Fetcher = Callable[[], dict]


def _http_fetcher(jwks_url: str, timeout: float) -> Fetcher:
    def getir() -> dict:
        # Şema JwksCache.__init__ içinde http/https ile sınırlandı.
        istek = urllib.request.Request(jwks_url, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(istek, timeout=timeout) as yanit:  # noqa: S310
            if yanit.status != 200:
                raise OSError(f"JWKS yanıtı {yanit.status}")
            return json.loads(yanit.read().decode("utf-8"))

    return getir


class JwksCache:
    def __init__(
        self,
        jwks_url: str,
        ttl_seconds: int = 600,
        *,
        fetcher: Fetcher | None = None,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 5.0,
        min_refresh_seconds: float = 5.0,
    ):
        sema = urllib.parse.urlsplit(jwks_url).scheme
        if sema not in ("http", "https"):
            raise ValueError("jwks_url yalnız http veya https olabilir")
        self.jwks_url = jwks_url
        self.ttl_seconds = int(ttl_seconds)
        self._fetch = fetcher or _http_fetcher(jwks_url, timeout)
        self._clock = clock
        self._min_refresh = float(min_refresh_seconds)
        self._lock = threading.Lock()
        self._keys: dict[str, object] = {}
        self._loaded_at: float | None = None
        self._forced_at: float | None = None

    def _expired(self) -> bool:
        return self._loaded_at is None or (self._clock() - self._loaded_at) >= self.ttl_seconds

    def _refresh_locked(self) -> None:
        veri = self._fetch()
        anahtarlar: dict[str, object] = {}
        for jwk in veri.get("keys", []):
            if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
                continue
            if jwk.get("alg", "RS256") != "RS256":
                continue
            kid = jwk.get("kid")
            if not kid:
                continue
            anahtarlar[kid] = jwt.PyJWK(jwk, algorithm="RS256").key
        self._keys = anahtarlar
        self._loaded_at = self._clock()

    def refresh(self) -> None:
        with self._lock:
            self._refresh_locked()

    def get_signing_key(self, kid: str):
        """`kid` için açık anahtarı döner. Bilinmiyorsa listeyi bir kez yeniler."""
        with self._lock:
            if self._expired():
                self._refresh_locked()
            anahtar = self._keys.get(kid)
            if anahtar is not None:
                return anahtar
            simdi = self._clock()
            yakinda_zorlandi = self._forced_at is not None and (simdi - self._forced_at) < self._min_refresh
            if not yakinda_zorlandi:
                self._forced_at = simdi
                self._refresh_locked()
                anahtar = self._keys.get(kid)
                if anahtar is not None:
                    return anahtar
        raise TokenError("unknown_kid")
