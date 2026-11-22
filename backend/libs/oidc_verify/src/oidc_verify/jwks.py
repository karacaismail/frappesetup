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

Bounds: one deadline of `total_timeout` seconds covers the whole download, from name resolution to the
end of the body. The download runs in a worker thread and the caller stops waiting when the time is
over; the connection is then cut (the per-operation socket `timeout` alone does not bound that).
A caller whose `kid` is cached and still inside the stale window never waits for the refresh lock: it
tries the refresh without blocking and serves the cached key when another thread holds the lock. A
caller without a usable key waits at most `wait_timeout` seconds and then raises `JwksUnavailable`.
The refresh lock is always released.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import threading
import time
import urllib.error
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect. A redirect could move the download to another host or to plain HTTP."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()  # the refused response still holds the socket
        raise OSError(f"JWKS redirect refused ({code})")


class _Deadline:
    """Cuts the open connection when the total download time is over.

    The waiting caller calls `cut` when the deadline is over. Shutting the socket down wakes the worker's
    read in any stage that has a socket: the TLS handshake, the status line, the headers and the body.
    """

    def __init__(self, end: float) -> None:
        self._lock = threading.Lock()
        self._conn: http.client.HTTPConnection | None = None
        self._connecting: socket.socket | None = None
        self._end = end
        self._cancelled = False

    @property
    def expired(self) -> bool:
        return self._cancelled or time.monotonic() >= self._end

    def attach(self, conn: http.client.HTTPConnection) -> None:
        with self._lock:
            if self.expired:
                raise TimeoutError("JWKS download exceeded total_timeout")
            self._conn = conn
        # http.client opens the socket through this attribute. The guarded version resolves the name
        # first and does not connect when the deadline passed during the resolution.
        conn._create_connection = self.create_connection  # type: ignore[attr-defined]

    def create_connection(self, address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):  # type: ignore[attr-defined]
        """Like socket.create_connection, but stops between name resolution and connect when expired.

        Python cannot interrupt a name lookup. The lookup itself may outlive the deadline; what follows
        it is skipped, so an expired download never opens a connection.
        """
        host, port = address
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        last_error: OSError | None = None
        for family, kind, proto, _canonical, target in infos:
            if self.expired:
                raise TimeoutError("JWKS download exceeded total_timeout")
            sock = socket.socket(family, kind, proto)
            try:
                if source_address:
                    sock.bind(source_address)
                with self._lock:
                    remaining = self._end - time.monotonic()
                    if self._cancelled or remaining <= 0:
                        raise TimeoutError("JWKS download exceeded total_timeout")
                    operation_timeout = None if timeout is socket._GLOBAL_DEFAULT_TIMEOUT else timeout  # type: ignore[attr-defined]
                    sock.settimeout(
                        remaining if operation_timeout is None else min(remaining, operation_timeout)
                    )
                    self._connecting = sock
                sock.connect(target)
                with self._lock:
                    if self.expired:
                        raise TimeoutError("JWKS download exceeded total_timeout")
                    sock.settimeout(operation_timeout)
                    if self._conn is not None:
                        self._conn.sock = sock
                return sock
            except OSError as error:
                last_error = error
                sock.close()
            finally:
                with self._lock:
                    self._connecting = None
        raise last_error or OSError("getaddrinfo returned no address")

    def cut(self) -> None:
        with self._lock:
            self._cancelled = True
            connecting = self._connecting
            sock = getattr(self._conn, "sock", None)
        if connecting is not None and connecting is not sock:
            connecting.close()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class _DeadlineHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, deadline: _Deadline) -> None:
        super().__init__()
        self._deadline = deadline

    def http_open(self, req):
        def connection(host, **kwargs):
            conn = http.client.HTTPConnection(host, **kwargs)
            self._deadline.attach(conn)
            return conn

        return self.do_open(connection, req)


class _DeadlineHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, deadline: _Deadline) -> None:
        super().__init__()
        self._deadline = deadline

    def https_open(self, req):
        def connection(host, **kwargs):
            conn = http.client.HTTPSConnection(host, **kwargs)
            self._deadline.attach(conn)
            return conn

        return self.do_open(connection, req, context=self._context)


def _is_development_host(host: str | None) -> bool:
    """`localhost`, a name under `.localhost` (RFC 6761) or a loopback address."""
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_url(jwks_url: str) -> None:
    """G-13: HTTPS only. Plain HTTP is an explicit exception for development addresses."""
    parts = urllib.parse.urlsplit(jwks_url)
    if parts.scheme == "https" and parts.hostname:
        return
    if parts.scheme == "http" and _is_development_host(parts.hostname):
        return
    raise ValueError("jwks_url must use https; plain http is allowed only for localhost and loopback")


def _http_fetcher(
    jwks_url: str,
    timeout: float,
    max_bytes: int = DEFAULT_MAX_BYTES,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
) -> Fetcher:
    """Builds the default fetcher.

    One deadline covers the whole download, from the first network step to the end of the body: name
    resolution, connect, the TLS handshake, the status line, the headers and the body. The download runs
    in a worker thread. The caller waits at most `total_timeout` seconds. When the time is over the
    caller gets `TimeoutError` at once, the connection is cut if one is open, and the worker's late
    result is thrown away. The worker itself ends within one socket `timeout` after the cut; name
    resolution cannot be cut and ends when the resolver gives up. The refresh throttle
    (`min_refresh_seconds`) keeps such abandoned workers rare. The body is capped at `max_bytes`.
    """

    def download(opener, request, deadline: _Deadline) -> dict:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            error.close()  # an error response still holds the socket
            raise OSError(f"JWKS response status {error.code}") from None
        with response:
            if response.status != 200:
                raise OSError(f"JWKS response status {response.status}")
            chunks: list[bytes] = []
            size = 0
            while True:
                if deadline.expired:
                    # Leaving the `with` block closes the response and the connection.
                    raise TimeoutError("JWKS download exceeded total_timeout")
                # read1 returns after one socket read. Read one byte past the cap to detect an oversized
                # body without buffering all of it.
                chunk = response.read1(min(_READ_CHUNK, max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("JWKS response exceeds the size limit")
            if deadline.expired:
                # A cut socket can end the body read with an empty chunk instead of an error.
                raise TimeoutError("JWKS download exceeded total_timeout")
            body = b"".join(chunks)
        return json.loads(body.decode("utf-8"))

    # At most one download per cache (third review). A call that comes while the previous download is
    # still alive waits for it at most total_timeout and then fails without starting a new one; the cache
    # then serves a cached key or raises JwksUnavailable. In the worst case one download stays open:
    # a name lookup that never returns.
    running: list[threading.Thread] = []
    running_lock = threading.Lock()

    def fetch() -> dict:
        # The URL was checked in JwksCache.__init__ (_check_url). The opener refuses redirects.
        # S310 checks the scheme of a URL opened by urllib: _check_url allows only https and dev http.
        request = urllib.request.Request(jwks_url, headers={"Accept": "application/json"})  # noqa: S310
        end = time.monotonic() + total_timeout
        deadline = _Deadline(end)
        opener = urllib.request.build_opener(
            _NoRedirect(), _DeadlineHTTPHandler(deadline), _DeadlineHTTPSHandler(deadline)
        )
        outcome: dict[str, object] = {}
        finished = threading.Event()

        def work() -> None:
            try:
                outcome["value"] = download(opener, request, deadline)
            except BaseException as error:
                outcome["error"] = error
            finally:
                finished.set()

        worker = threading.Thread(target=work, name="oidc-verify-jwks-download", daemon=True)
        with running_lock:
            if running and running[0].is_alive():
                # A cut download ends within moments. Wait for it at most total_timeout, never longer.
                running[0].join(max(0.0, end - time.monotonic()))
                if running[0].is_alive():
                    raise TimeoutError("the previous JWKS download is still running")
            if deadline.expired:
                raise TimeoutError("JWKS download exceeded total_timeout")
            running[:] = [worker]
            worker.start()
        if not finished.wait(max(0.0, end - time.monotonic())) or deadline.expired:
            deadline.cut()
            raise TimeoutError("JWKS download exceeded total_timeout")
        if "error" in outcome:
            error = outcome["error"]
            if deadline.expired and isinstance(error, OSError):
                raise TimeoutError("JWKS download exceeded total_timeout") from error
            raise error  # type: ignore[misc]
        return outcome["value"]  # type: ignore[return-value]

    return fetch


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
        _check_url(jwks_url)
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

    def _attempt_refresh(self, seen_generation: int, *, forced: bool, wait: bool = True) -> bool | None:
        """Runs at most one fetch. Returns True when a fetch was attempted since `seen_generation`.

        Returns False when the failure throttle skipped the fetch, and None when the refresh lock could
        not be taken within `wait_timeout` (another thread's fetch is still running). The caller decides
        whether a cached key may still be served in that case.

        The network call happens outside `_state_lock`, so readers with a cached `kid` are never blocked.
        Throttling (`min_refresh_seconds`) is applied inside `_refresh_lock` so it is race free.
        """
        if wait:
            acquired = self._refresh_lock.acquire(timeout=self.wait_timeout)
        else:
            acquired = self._refresh_lock.acquire(blocking=False)
        if not acquired:
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
        """Returns the public key for `kid`. Refreshes the list once when the `kid` is unknown."""
        key, expired, generation = self._lookup(kid)
        if key is not None and not expired:
            return key
        attempted: bool | None = False
        if expired:
            if key is not None and self._usable():
                # A valid cached key never waits for the refresh lock. Try the refresh without blocking:
                # when another thread already runs it, serve the cached key at once (merge review O4).
                attempted = self._attempt_refresh(generation, forced=False, wait=False)
                if attempted is None:
                    return key
            else:
                attempted = self._attempt_refresh(generation, forced=False)
            if not self._usable():
                raise JwksUnavailable("Anahtar listesi alınamadı")
            key, _, generation = self._lookup(kid)
            if key is not None:
                return key
            if attempted is None:
                # Waited `wait_timeout` for another thread's fetch and the kid is still not cached.
                raise JwksUnavailable("Anahtar listesi alınamadı")
        if not attempted:
            attempted = self._attempt_refresh(generation, forced=True)
            key = self._lookup(kid)[0]
            if key is not None:
                return key
            if attempted is None:
                raise JwksUnavailable("Anahtar listesi alınamadı")
        raise TokenError("unknown_kid")
