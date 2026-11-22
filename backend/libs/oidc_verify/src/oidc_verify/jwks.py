"""Anahtar listesi önbelleği.

Liste `ttl_seconds` süresince saklanır. Bilinmeyen `kid` gelince liste bir kez yenilenir.
Art arda gelen bilinmeyen `kid` istekleri listeyi en çok `min_refresh_seconds` aralığıyla yeniletir.

Çekim başarısız olursa önbellekteki eski anahtarlar kullanılmaya devam eder.
Başarısız denemeden sonra yeni deneme en erken `min_refresh_seconds` sonra yapılır.
Önbellekte hiç anahtar yoksa `JwksUnavailable` yükselir.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

import jwt

from oidc_verify.hatalar import JwksUnavailable, TokenError

Fetcher = Callable[[], dict]

# PyJWT 2.13 bozuk JWK için ValueError ya da TypeError verir. PyJWT 2.15 bunları InvalidKeyError içine sarar.
_JWK_HATALARI = (jwt.exceptions.PyJWTError, ValueError, TypeError)


def _http_fetcher(jwks_url: str, timeout: float) -> Fetcher:
    def getir() -> dict:
        # Şema JwksCache.__init__ içinde http/https ile sınırlandı.
        istek = urllib.request.Request(jwks_url, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(istek, timeout=timeout) as yanit:  # noqa: S310
            if yanit.status != 200:
                raise OSError(f"JWKS yanıtı {yanit.status}")
            return json.loads(yanit.read().decode("utf-8"))

    return getir


def _anahtarlari_ayikla(veri: object) -> dict[str, object]:
    """Listeden RS256 imza anahtarlarını çıkarır. Bozuk kayıt atlanır. Bozuk liste hata verir."""
    if not isinstance(veri, dict) or not isinstance(veri.get("keys"), list):
        raise ValueError("JWKS gövdesi beklenen biçimde değil")
    anahtarlar: dict[str, object] = {}
    for jwk in veri["keys"]:
        if not isinstance(jwk, dict):
            continue
        if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
            continue
        if jwk.get("alg", "RS256") != "RS256":
            continue
        kid = jwk.get("kid")
        if not kid or not isinstance(kid, str):
            continue
        try:
            anahtarlar[kid] = jwt.PyJWK(jwk, algorithm="RS256").key
        except _JWK_HATALARI:
            # Tek bozuk kayıt bütün listeyi düşürmez.
            continue
    return anahtarlar


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
        self._failed_at: float | None = None

    def _expired(self) -> bool:
        return self._loaded_at is None or (self._clock() - self._loaded_at) >= self.ttl_seconds

    def _yakinda(self, an: float | None) -> bool:
        return an is not None and (self._clock() - an) < self._min_refresh

    def _refresh_locked(self) -> None:
        """Listeyi çeker. Çekim başarısızsa eski anahtarlar kalır. Hiç anahtar yoksa hata yükselir."""
        try:
            anahtarlar = _anahtarlari_ayikla(self._fetch())
        except Exception as hata:
            # Sağlayıcı dışarıdan verilebilir. Hangi hatayı verirse versin eski anahtarlar korunur.
            self._failed_at = self._clock()
            if not self._keys:
                raise JwksUnavailable("Anahtar listesi alınamadı") from hata
            return
        self._keys = anahtarlar
        self._loaded_at = self._clock()
        self._failed_at = None

    def refresh(self) -> None:
        with self._lock:
            self._refresh_locked()

    def get_signing_key(self, kid: str):
        """`kid` için açık anahtarı döner. Bilinmiyorsa listeyi bir kez yeniler."""
        with self._lock:
            yenilendi = False
            if self._expired():
                if self._yakinda(self._failed_at):
                    # Son deneme az önce başarısız oldu. Eski anahtar varsa onunla devam edilir.
                    if not self._keys:
                        raise JwksUnavailable("Anahtar listesi alınamadı")
                else:
                    self._refresh_locked()
                    yenilendi = True
            anahtar = self._keys.get(kid)
            if anahtar is not None:
                return anahtar
            if not yenilendi and not self._yakinda(self._forced_at) and not self._yakinda(self._failed_at):
                self._forced_at = self._clock()
                self._refresh_locked()
                anahtar = self._keys.get(kid)
                if anahtar is not None:
                    return anahtar
        raise TokenError("unknown_kid")
