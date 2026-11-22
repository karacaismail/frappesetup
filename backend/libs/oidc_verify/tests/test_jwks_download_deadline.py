"""Regression tests for finding O4 (second review): total download deadline and bounded waiting.

`urlopen(timeout=...)` bounds each socket operation only. A server that trickles a few bytes before
every timeout could keep the refresh lock held without bound. These tests use a loopback HTTP server
that trickles a JWKS body, and fake fetchers that block on events, to check that:

- the HTTP fetcher gives up at `total_timeout` and the refresh lock is released,
- a caller that has to wait for an in-flight refresh gives up at `wait_timeout`,
- two refreshes started at the same moment result in one network fetch.
"""

import http.server
import json
import threading
import time
import unittest

from keys import ISSUER, Anahtar, FakeJwks, access_payload

from oidc_verify import JwksCache, JwksUnavailable, TokenError, verify_access_token

JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"

# How long the trickling handler keeps sending before it closes the connection on its own.
TRICKLE_SECONDS = 3.0
TRICKLE_INTERVAL = 0.2


class _TricklingJwksHandler(http.server.BaseHTTPRequestHandler):
    """Sends a valid JWKS body either at once (`trickle` False) or a few bytes at a time.

    While trickling, the body has no Content-Length, so the client reads until the connection closes.
    The handler stops when the client goes away (broken pipe) or after `TRICKLE_SECONDS`.
    """

    body = b""
    trickle = True

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if not self.trickle:
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body)
            return
        self.end_headers()
        deadline = time.monotonic() + TRICKLE_SECONDS
        offset = 0
        try:
            while time.monotonic() < deadline:
                chunk = self.body[offset : offset + 3]
                if not chunk:
                    chunk = b" "
                self.wfile.write(chunk)
                self.wfile.flush()
                offset += 3
                time.sleep(TRICKLE_INTERVAL)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def log_message(self, *args):
        return


class _ServerMixin:
    def serve(self, key: Anahtar, *, trickle: bool = True) -> tuple[type, str]:
        body = json.dumps({"keys": [key.jwk()]}).encode("utf-8")
        handler = type("Handler", (_TricklingJwksHandler,), {"body": body, "trickle": trickle})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return handler, f"http://127.0.0.1:{server.server_address[1]}/certs"

    def access(self, token, cache):
        return verify_access_token(
            token,
            cache=cache,
            issuer=ISSUER,
            audience="site-tenant1",
            allowed_azp={"identity-sync"},
            leeway=30,
        )


class DownloadDeadlineTest(_ServerMixin, unittest.TestCase):
    """The HTTP fetcher stops reading at `total_timeout` even when bytes keep trickling in."""

    def test_defaults(self):
        cache = JwksCache("https://identity.example/certs")
        self.assertEqual(cache.total_timeout, 10.0)
        self.assertEqual(cache.wait_timeout, 11.0)
        self.assertEqual(JwksCache("https://identity.example/certs", total_timeout=3).wait_timeout, 4.0)
        self.assertEqual(JwksCache("https://identity.example/certs", wait_timeout=2).wait_timeout, 2.0)

    def test_non_positive_timeouts_are_rejected(self):
        with self.assertRaises(ValueError):
            JwksCache("https://identity.example/certs", total_timeout=0)
        with self.assertRaises(ValueError):
            JwksCache("https://identity.example/certs", wait_timeout=-1)

    def test_cold_cache_gives_up_at_total_timeout_and_releases_lock(self):
        key = Anahtar("kid-1")
        handler, url = self.serve(key)
        cache = JwksCache(url, ttl_seconds=600, timeout=0.3, total_timeout=0.6, min_refresh_seconds=0)
        token = key.sign(access_payload())
        begin = time.monotonic()
        with self.assertRaises(JwksUnavailable):
            self.access(token, cache)
        elapsed = time.monotonic() - begin
        self.assertLess(elapsed, 2.5, f"cold-cache caller waited {elapsed:.3f}s on a trickling server")
        self.assertGreaterEqual(elapsed, 0.5, "the deadline fired before total_timeout")
        self.assertFalse(cache._refresh_lock.locked(), "refresh lock still held after the deadline")
        # The same server now answers at once: the next call succeeds, so nothing stayed wedged.
        handler.trickle = False
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")

    def test_warm_cache_serves_cached_kid_during_slow_refresh_and_keeps_keys(self):
        key = Anahtar("kid-1")
        handler, url = self.serve(key, trickle=False)
        now = [1000.0]
        cache = JwksCache(
            url,
            ttl_seconds=600,
            timeout=0.3,
            total_timeout=0.6,
            clock=lambda: now[0],
            min_refresh_seconds=0,
        )
        token = key.sign(access_payload())
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
        handler.trickle = True
        now[0] += 601
        refresh_done = threading.Event()
        outcome: list[object] = []

        def refresher():
            try:
                outcome.append(self.access(token, cache)["azp"])
            except Exception as error:
                outcome.append(error)
            finally:
                refresh_done.set()

        thread = threading.Thread(target=refresher, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 2.0
            while not cache._refresh_lock.locked() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(cache._refresh_lock.locked(), "the slow refresh did not start")
            begin = time.monotonic()
            self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
            waited = time.monotonic() - begin
            self.assertLess(waited, 0.5, f"cached-kid reader waited {waited:.3f}s for the slow refresh")
            self.assertTrue(refresh_done.wait(5.0), "the slow refresh did not finish within the bound")
        finally:
            thread.join(5.0)
        # The refresh failed at the deadline; the stale key is still served from the cache.
        self.assertEqual(outcome, ["identity-sync"])
        self.assertIn("kid-1", cache._keys)
        self.assertFalse(cache._refresh_lock.locked())

    def test_expired_stale_window_with_slow_server_fails_within_bound(self):
        key = Anahtar("kid-1")
        handler, url = self.serve(key, trickle=False)
        now = [1000.0]
        cache = JwksCache(
            url,
            ttl_seconds=600,
            timeout=0.3,
            total_timeout=0.6,
            clock=lambda: now[0],
            max_stale_seconds=60,
            min_refresh_seconds=0,
        )
        token = key.sign(access_payload())
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
        handler.trickle = True
        now[0] += 600 + 61
        begin = time.monotonic()
        with self.assertRaises(JwksUnavailable):
            self.access(token, cache)
        elapsed = time.monotonic() - begin
        self.assertLess(elapsed, 2.5, f"caller past the stale window waited {elapsed:.3f}s")
        self.assertFalse(cache._refresh_lock.locked())


class BoundedWaitTest(_ServerMixin, unittest.TestCase):
    """Callers that need a refresh but find one in flight wait at most `wait_timeout`."""

    def test_simultaneous_refresh_starts_fetch_once(self):
        key = Anahtar("kid-1")
        inner = FakeJwks(key)
        in_fetch = threading.Event()
        proceed = threading.Event()

        def fetcher():
            data = inner()
            in_fetch.set()
            self.assertTrue(proceed.wait(5.0))
            return data

        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=fetcher)
        token = key.sign(access_payload())
        gate = threading.Barrier(2)
        results: list[object] = []
        lock = threading.Lock()

        def worker():
            gate.wait()
            try:
                result = self.access(token, cache)["azp"]
            except Exception as error:
                result = error
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        self.assertTrue(in_fetch.wait(5.0))
        # Give the second caller time to arrive at the refresh lock while the first fetch is in flight.
        time.sleep(0.2)
        proceed.set()
        for thread in threads:
            thread.join(5.0)
        self.assertEqual(results, ["identity-sync"] * 2)
        self.assertEqual(inner.cagri, 1)
        self.assertFalse(cache._refresh_lock.locked())

    def test_unknown_kid_caller_gives_up_at_wait_timeout(self):
        key = Anahtar("kid-1")
        new_key = Anahtar("kid-2")
        inner = FakeJwks(key)
        in_fetch = threading.Event()
        release = threading.Event()

        def fetcher():
            data = inner()
            if inner.cagri > 1:
                in_fetch.set()
                self.assertTrue(release.wait(10.0))
            return data

        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=fetcher, wait_timeout=0.5)
        self.assertEqual(self.access(key.sign(access_payload()), cache)["azp"], "identity-sync")
        inner.keys.append(new_key)
        token = new_key.sign(access_payload())
        first: list[object] = []

        def first_caller():
            try:
                first.append(self.access(token, cache)["azp"])
            except Exception as error:
                first.append(error)

        thread = threading.Thread(target=first_caller, daemon=True)
        thread.start()
        try:
            self.assertTrue(in_fetch.wait(5.0))
            begin = time.monotonic()
            with self.assertRaises(JwksUnavailable):
                self.access(token, cache)
            elapsed = time.monotonic() - begin
        finally:
            release.set()
            thread.join(5.0)
        self.assertGreaterEqual(elapsed, 0.4, "the waiting caller returned before wait_timeout")
        self.assertLess(elapsed, 2.0, f"the waiting caller waited {elapsed:.3f}s, bound is 0.5s")
        # The first refresh completed once released, and the lock is free again.
        self.assertEqual(first, ["identity-sync"])
        self.assertEqual(inner.cagri, 2)
        self.assertFalse(cache._refresh_lock.locked())
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")

    def test_expired_cached_kid_waiter_falls_back_to_stale_key_on_wait_timeout(self):
        key = Anahtar("kid-1")
        inner = FakeJwks(key)
        in_fetch = threading.Event()
        release = threading.Event()
        now = [1000.0]

        def fetcher():
            data = inner()
            if inner.cagri > 1:
                in_fetch.set()
                self.assertTrue(release.wait(10.0))
            return data

        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=fetcher, clock=lambda: now[0], wait_timeout=0.3)
        token = key.sign(access_payload())
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
        now[0] += 601
        thread = threading.Thread(target=self.access, args=(token, cache), daemon=True)
        thread.start()
        try:
            self.assertTrue(in_fetch.wait(5.0))
            # Force the waiting path: the lock is held, so the attempt times out and falls back.
            begin = time.monotonic()
            result = cache._attempt_refresh(cache._generation, forced=False)
            elapsed = time.monotonic() - begin
            self.assertIsNone(result)
            self.assertLess(elapsed, 2.0)
            # Public path: cached kid is served despite the in-flight refresh.
            self.assertEqual(cache.get_signing_key("kid-1"), cache._keys["kid-1"])
        finally:
            release.set()
            thread.join(5.0)
        self.assertFalse(cache._refresh_lock.locked())

    def test_fetcher_exception_releases_lock(self):
        inner = FakeJwks(Anahtar("kid-1"))
        inner.error = RuntimeError("boom")
        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=inner, min_refresh_seconds=0)
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("kid-1")
        self.assertFalse(cache._refresh_lock.locked())
        inner.error = None
        self.assertIsNotNone(cache.get_signing_key("kid-1"))
        with self.assertRaises(TokenError) as caught:
            cache.get_signing_key("kid-9")
        self.assertEqual(caught.exception.code, "unknown_kid")


if __name__ == "__main__":
    unittest.main()
