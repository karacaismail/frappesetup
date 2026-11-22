"""Merge review finding O4: the total download deadline covers every stage, and a caller with a valid
cached key never waits for the refresh lock.

1. A server that sends the status line and then trickles header bytes must not keep a refresh alive past
   `total_timeout`. The per-operation socket timeout alone does not stop it.
2. Two callers with an expired but still usable cached key can both see the refresh lock free. The one
   that loses the race must serve the cached key at once, not wait `wait_timeout`.
"""

import socketserver
import threading
import time
import unittest

from anahtarlar import Anahtar, SahteJwks

from oidc_verify import JwksCache, JwksUnavailable

TRICKLE_SECONDS = 4.0


class _SlowHeaderHandler(socketserver.BaseRequestHandler):
    """Sends a status line, then one header byte every 0.2 seconds. Never finishes the headers."""

    def handle(self):
        self.request.recv(4096)
        try:
            self.request.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            deadline = time.monotonic() + TRICKLE_SECONDS
            while time.monotonic() < deadline:
                self.request.sendall(b"a")
                time.sleep(0.2)
        except OSError:
            return


class SlowHeaderTest(unittest.TestCase):
    def setUp(self):
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SlowHeaderHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_address[1]}/certs"

    def test_total_deadline_covers_the_header_stage(self):
        cache = JwksCache(self.url, timeout=1.0, total_timeout=0.8, min_refresh_seconds=0)
        begin = time.monotonic()
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("kid-1")
        elapsed = time.monotonic() - begin
        self.assertLess(elapsed, 2.0, f"refresh took {elapsed:.2f} s; total_timeout is 0.8 s")
        self.assertFalse(cache._refresh_lock.locked())


class _RacingLock:
    """A real lock whose `locked()` answers False once, as if the caller checked just before the other
    thread took it."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lie = True

    def acquire(self, blocking=True, timeout=-1):
        return self._lock.acquire(blocking, timeout)

    def release(self):
        self._lock.release()

    def locked(self):
        if self._lie:
            self._lie = False
            return False
        return self._lock.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


class ConcurrentStartTest(unittest.TestCase):
    def test_caller_with_a_usable_cached_key_does_not_wait_for_the_lock(self):
        key = Anahtar("kid-1")
        inner = SahteJwks(key)
        in_fetch = threading.Event()
        release = threading.Event()
        now = [1000.0]

        def fetcher():
            data = inner()
            if inner.cagri > 1:
                in_fetch.set()
                release.wait(10.0)
            return data

        cache = JwksCache(
            "https://idp.example.test/certs",
            ttl_seconds=600,
            fetcher=fetcher,
            clock=lambda: now[0],
            wait_timeout=5.0,
            min_refresh_seconds=0,
        )
        cached = cache.get_signing_key("kid-1")
        now[0] += 601  # expired, still inside the stale window
        first = threading.Thread(target=cache.get_signing_key, args=("kid-1",), daemon=True)
        first.start()
        try:
            self.assertTrue(in_fetch.wait(5.0))
            racing = _RacingLock()
            racing._lock = cache._refresh_lock  # the lock the first caller already holds
            cache._refresh_lock = racing
            begin = time.monotonic()
            self.assertIs(cache.get_signing_key("kid-1"), cached)
            elapsed = time.monotonic() - begin
            self.assertLess(elapsed, 0.5, f"waited {elapsed:.2f} s for the refresh lock")
        finally:
            release.set()
            first.join(5.0)


class RotatedKeyTest(unittest.TestCase):
    def test_key_removed_by_the_refresh_is_not_served(self):
        old, new = Anahtar("kid-old"), Anahtar("kid-new")
        provider = SahteJwks(old)
        now = [1000.0]
        cache = JwksCache(
            "https://idp.example.test/certs",
            ttl_seconds=600,
            fetcher=provider,
            clock=lambda: now[0],
            min_refresh_seconds=0,
        )
        cache.get_signing_key("kid-old")
        provider.anahtarlar = [new]  # the identity server rotated the old key out
        now[0] += 601
        from oidc_verify import TokenError

        with self.assertRaises(TokenError):
            cache.get_signing_key("kid-old")


if __name__ == "__main__":
    unittest.main()
