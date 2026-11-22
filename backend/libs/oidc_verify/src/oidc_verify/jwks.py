"""Anahtar listesi önbelleği.

Liste `ttl_seconds` süresince saklanır. Bilinmeyen `kid` gelince liste bir kez yenilenir.
Art arda gelen bilinmeyen `kid` istekleri listeyi en çok `min_refresh_seconds` aralığıyla yeniletir.

Çekim başarısız olursa önbellekteki eski anahtarlar kullanılmaya devam eder.
Başarısız denemeden sonra yeni deneme en erken `min_refresh_seconds` sonra yapılır.
Önbellekte hiç anahtar yoksa `JwksUnavailable` yükselir.

Stale keys are served for at most `ttl_seconds + max_stale_seconds` after the last successful load.
Past that window every lookup raises `JwksUnavailable` until a fetch succeeds again.

Locking: `_state_lock` guards the key dict and timestamps and is held only briefly. `_refresh_lock`
serialises network fetches so at most one runs at a time. A reader whose `kid` is cached never waits
for an in-flight fetch; readers with an unknown `kid` wait for the running fetch and then look again.

Bounds: the HTTP fetcher gives up once the whole download has taken `total_timeout` seconds, however
slowly the server trickles bytes (the per-operation socket `timeout` alone does not bound that). A caller
that must wait for an in-flight refresh waits at most `wait_timeout` seconds; on timeout it serves a
cached key inside the stale window or raises `JwksUnavailable`. The refresh lock is always released.
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

DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_TOTAL_TIMEOUT = 10.0
# Read the body in pieces so the deadline is checked between socket reads.
_READ_CHUNK = 16_384

# PyJWT 2.13 bozuk JWK için ValueError ya da TypeError verir. PyJWT 2.15 bunları InvalidKeyError içine sarar.
_JWK_HATALARI = (jwt.exceptions.PyJWTError, ValueError, TypeError)


def _http_fetcher(
    jwks_url: str,
    timeout: float,
    max_bytes: int = DEFAULT_MAX_BYTES,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
) -> Fetcher:
    """Builds the default fetcher.

    `timeout` bounds each socket operation (connect, header read, one body read). `total_timeout` bounds
    the whole body download: a server that sends a few bytes before every socket timeout cannot keep the
    fetch alive. The worst case is `total_timeout + timeout`. The body is capped at `max_bytes`.
    """

    def getir() -> dict:
        # Şema JwksCache.__init__ içinde http/https ile sınırlandı.
        istek = urllib.request.Request(jwks_url, headers={"Accept": "application/json"})  # noqa: S310
        deadline = time.monotonic() + total_timeout
        with urllib.request.urlopen(istek, timeout=timeout) as yanit:  # noqa: S310
            if yanit.status != 200:
                raise OSError(f"JWKS yanıtı {yanit.status}")
            parcalar: list[bytes] = []
            uzunluk = 0
            while True:
                if time.monotonic() >= deadline:
                    # Leaving the `with` block closes the response and the connection.
                    raise TimeoutError("JWKS download exceeded total_timeout")
                # read1 returns after one socket read, so a trickling server cannot block this call
                # for longer than `timeout`. Read one byte past the cap to detect an oversized body
                # without buffering all of it.
                parca = yanit.read1(min(_READ_CHUNK, max_bytes + 1 - uzunluk))
                if not parca:
                    break
                parcalar.append(parca)
                uzunluk += len(parca)
                if uzunluk > max_bytes:
                    raise ValueError("JWKS response exceeds the size limit")
            govde = b"".join(parcalar)
        return json.loads(govde.decode("utf-8"))

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
        max_stale_seconds: int = 3600,
        max_bytes: int = DEFAULT_MAX_BYTES,
        total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
        wait_timeout: float | None = None,
    ):
        sema = urllib.parse.urlsplit(jwks_url).scheme
        if sema not in ("http", "https"):
            raise ValueError("jwks_url yalnız http veya https olabilir")
        if int(max_stale_seconds) < 0:
            raise ValueError("max_stale_seconds must not be negative")
        if int(max_bytes) <= 0:
            raise ValueError("max_bytes must be positive")
        if float(total_timeout) <= 0:
            raise ValueError("total_timeout must be positive")
        if wait_timeout is None:
            wait_timeout = float(total_timeout) + 1.0
        if float(wait_timeout) <= 0:
            raise ValueError("wait_timeout must be positive")
        self.jwks_url = jwks_url
        self.ttl_seconds = int(ttl_seconds)
        self.max_stale_seconds = int(max_stale_seconds)
        self.max_bytes = int(max_bytes)
        self.total_timeout = float(total_timeout)
        self.wait_timeout = float(wait_timeout)
        self._fetch = fetcher or _http_fetcher(jwks_url, timeout, self.max_bytes, self.total_timeout)
        self._clock = clock
        self._min_refresh = float(min_refresh_seconds)
        # Short lock for the dict and timestamps; separate lock so only one fetch runs at a time.
        self._state_lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._keys: dict[str, object] = {}
        self._loaded_at: float | None = None
        self._forced_at: float | None = None
        self._failed_at: float | None = None
        # Incremented on every fetch attempt; lets a waiting thread see that another thread already tried.
        self._generation = 0

    # --- helpers that expect _state_lock to be held ---

    def _expired(self) -> bool:
        return self._loaded_at is None or (self._clock() - self._loaded_at) >= self.ttl_seconds

    def _too_stale(self) -> bool:
        """True once the last good load is older than ttl_seconds + max_stale_seconds."""
        if self._loaded_at is None:
            return False
        return (self._clock() - self._loaded_at) >= self.ttl_seconds + self.max_stale_seconds

    def _yakinda(self, an: float | None) -> bool:
        return an is not None and (self._clock() - an) < self._min_refresh

    def _lookup(self, kid: str) -> tuple[object | None, bool, int]:
        with self._state_lock:
            return self._keys.get(kid), self._expired(), self._generation

    def _usable(self) -> bool:
        """True when cached keys exist and are still inside the stale window."""
        with self._state_lock:
            return bool(self._keys) and not self._too_stale()

    # --- refresh ---

    def _attempt_refresh(self, seen_generation: int, *, forced: bool) -> bool | None:
        """Runs at most one fetch. Returns True when a fetch was attempted since `seen_generation`.

        Returns False when the failure throttle skipped the fetch, and None when the refresh lock could
        not be taken within `wait_timeout` (another thread's fetch is still running). The caller decides
        whether a cached key may still be served in that case.

        The network call happens outside `_state_lock`, so readers with a cached `kid` are never blocked.
        Throttling (`min_refresh_seconds`) is applied inside `_refresh_lock` so it is race free.
        """
        if not self._refresh_lock.acquire(timeout=self.wait_timeout):
            return None
        try:
            with self._state_lock:
                if self._generation != seen_generation:
                    # Another thread already fetched while this one waited for the lock.
                    return True
                if self._yakinda(self._failed_at) or (forced and self._yakinda(self._forced_at)):
                    return False
                if forced:
                    self._forced_at = self._clock()
            try:
                anahtarlar = _anahtarlari_ayikla(self._fetch())
            except Exception:
                # Sağlayıcı dışarıdan verilebilir. Hangi hatayı verirse versin eski anahtarlar korunur.
                with self._state_lock:
                    self._failed_at = self._clock()
                    self._generation += 1
                return True
            with self._state_lock:
                self._keys = anahtarlar
                self._loaded_at = self._clock()
                self._failed_at = None
                self._generation += 1
            return True
        finally:
            self._refresh_lock.release()

    def refresh(self) -> None:
        """Fetches the list now (subject to the failure throttle). Raises when no usable keys remain."""
        with self._state_lock:
            generation = self._generation
        self._attempt_refresh(generation, forced=False)
        if not self._usable():
            raise JwksUnavailable("Anahtar listesi alınamadı")

    def get_signing_key(self, kid: str):
        """`kid` için açık anahtarı döner. Bilinmiyorsa listeyi bir kez yeniler."""
        anahtar, expired, generation = self._lookup(kid)
        if anahtar is not None and not expired:
            return anahtar
        attempted: bool | None = False
        if expired:
            if anahtar is not None and self._refresh_lock.locked() and self._usable():
                # A refresh is already running in another thread. Serve the cached key without waiting.
                return anahtar
            attempted = self._attempt_refresh(generation, forced=False)
            if not self._usable():
                raise JwksUnavailable("Anahtar listesi alınamadı")
            anahtar, _, generation = self._lookup(kid)
            if anahtar is not None:
                return anahtar
            if attempted is None:
                # Waited `wait_timeout` for another thread's fetch and the kid is still not cached.
                raise JwksUnavailable("Anahtar listesi alınamadı")
        if not attempted:
            attempted = self._attempt_refresh(generation, forced=True)
            anahtar = self._lookup(kid)[0]
            if anahtar is not None:
                return anahtar
            if attempted is None:
                raise JwksUnavailable("Anahtar listesi alınamadı")
        raise TokenError("unknown_kid")
