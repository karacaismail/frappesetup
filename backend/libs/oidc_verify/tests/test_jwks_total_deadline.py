"""Merge review finding O4: the total download deadline covers every stage, and a caller with a valid
cached key never waits for the refresh lock.

Second review: the deadline starts at the first network step. Name resolution and the TLS handshake are
inside it too, and the call and the refresh lock are free again when it is over.

1. A server that sends the status line and then trickles header bytes must not keep a refresh alive past
   `total_timeout`. The per-operation socket timeout alone does not stop it.
2. Two callers with an expired but still usable cached key can both see the refresh lock free. The one
   that loses the race must serve the cached key at once, not wait `wait_timeout`.
"""

import socket
import socketserver
import threading
import time
import unittest
from unittest.mock import Mock, patch

from anahtarlar import Anahtar, SahteJwks

from oidc_verify import JwksCache, JwksUnavailable
from oidc_verify.jwks import _Deadline, _http_fetcher

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


class SlowNameResolutionTest(unittest.TestCase):
    def test_total_deadline_covers_name_resolution(self):
        real = socket.getaddrinfo
        started = threading.Event()

        def slow_getaddrinfo(*args, **kwargs):
            started.set()
            time.sleep(TRICKLE_SECONDS)
            return real(*args, **kwargs)

        socket.getaddrinfo = slow_getaddrinfo
        self.addCleanup(setattr, socket, "getaddrinfo", real)
        cache = JwksCache(
            "https://slow-dns.example.test/certs", timeout=5.0, total_timeout=0.8, min_refresh_seconds=0
        )
        begin = time.monotonic()
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("kid-1")
        elapsed = time.monotonic() - begin
        self.assertTrue(started.is_set(), "the download must have started name resolution")
        self.assertLess(elapsed, 2.0, f"refresh took {elapsed:.2f} s; total_timeout is 0.8 s")
        self.assertFalse(cache._refresh_lock.locked())


class _SilentTlsHandler(socketserver.BaseRequestHandler):
    """Accepts the TCP connection, reads the TLS ClientHello and never answers it."""

    def handle(self):
        try:
            self.request.recv(4096)
            time.sleep(TRICKLE_SECONDS)
        except OSError:
            return


class SlowTlsHandshakeTest(unittest.TestCase):
    def setUp(self):
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SilentTlsHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"https://127.0.0.1:{server.server_address[1]}/certs"

    def test_total_deadline_covers_the_tls_handshake(self):
        cache = JwksCache(self.url, timeout=5.0, total_timeout=0.8, min_refresh_seconds=0)
        begin = time.monotonic()
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("kid-1")
        elapsed = time.monotonic() - begin
        self.assertLess(elapsed, 2.0, f"refresh took {elapsed:.2f} s; total_timeout is 0.8 s")
        self.assertFalse(cache._refresh_lock.locked())
        # The next call is not blocked by the abandoned download.
        begin = time.monotonic()
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("kid-1")
        self.assertLess(time.monotonic() - begin, 2.0)


DOWNLOAD_THREAD = "oidc-verify-jwks-download"


def _open_downloads() -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == DOWNLOAD_THREAD and thread.is_alive())


class InFlightLimitTest(unittest.TestCase):
    """Third review: at most one download runs per cache, and an expired one never connects."""

    def setUp(self):
        self.real = socket.getaddrinfo
        self.addCleanup(setattr, socket, "getaddrinfo", self.real)
        # Let downloads left over from earlier tests finish first.
        deadline = time.monotonic() + TRICKLE_SECONDS + 2
        while _open_downloads() and time.monotonic() < deadline:
            time.sleep(0.1)

    def test_cut_during_socket_setup_prevents_connect(self):
        deadline = _Deadline(time.monotonic() + 1)
        connection_socket = Mock()

        def create_socket(*args):
            deadline.cut()
            return connection_socket

        address = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))
        with patch.object(socket, "getaddrinfo", return_value=[address]):
            with patch.object(socket, "socket", side_effect=create_socket):
                with self.assertRaises(TimeoutError):
                    deadline.create_connection(("example.test", 443), timeout=1)
        connection_socket.connect.assert_not_called()
        connection_socket.close.assert_called_once()

    def test_replacement_download_uses_only_the_remaining_budget(self):
        old_worker = Mock()
        old_worker.is_alive.side_effect = [True, False]
        new_worker = Mock()
        old_finished = Mock()
        new_finished = Mock()
        now = 0.0

        def consume_budget(seconds):
            nonlocal now
            now += seconds
            return False

        old_finished.wait.side_effect = consume_budget
        old_worker.join.side_effect = lambda timeout: consume_budget(0.75)
        new_finished.wait.side_effect = consume_budget

        with (
            patch.object(time, "monotonic", side_effect=lambda: now),
            patch.object(threading, "Thread", side_effect=[old_worker, new_worker]),
            patch.object(threading, "Event", side_effect=[old_finished, new_finished]),
        ):
            fetch = _http_fetcher("https://example.test/certs", timeout=1, total_timeout=1)
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    fetch()
        new_finished.wait.assert_called_once_with(0.25)

    def test_repeated_timeouts_keep_at_most_one_open_download(self):
        def slow_getaddrinfo(*args, **kwargs):
            time.sleep(TRICKLE_SECONDS)
            return self.real(*args, **kwargs)

        socket.getaddrinfo = slow_getaddrinfo
        cache = JwksCache(
            "https://slow-dns.example.test/certs",
            timeout=5.0,
            total_timeout=0.3,
            min_refresh_seconds=0,
            wait_timeout=0.3,
        )
        peak = 0
        for _ in range(4):
            begin = time.monotonic()
            with self.assertRaises(JwksUnavailable):
                cache.get_signing_key("kid-1")
            self.assertLess(time.monotonic() - begin, 1.5)
            peak = max(peak, _open_downloads())
        self.assertLessEqual(peak, 1, f"{peak} downloads were open at the same time")

    def test_expired_download_does_not_connect_after_name_resolution(self):
        accepted = []
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SilentTlsHandler)
        server.daemon_threads = True
        original_handle = _SilentTlsHandler.handle
        server.RequestHandlerClass = type(
            "Recording",
            (_SilentTlsHandler,),
            {"handle": lambda handler: (accepted.append(1), original_handle(handler))},
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def late_getaddrinfo(host, *args, **kwargs):
            time.sleep(1.0)  # resolution finishes after the 0.3 second deadline
            return self.real("127.0.0.1", port, *args[1:], **kwargs)

        socket.getaddrinfo = late_getaddrinfo
        cache = JwksCache(
            f"https://late-dns.example.test:{port}/certs",
            timeout=5.0,
            total_timeout=0.3,
            min_refresh_seconds=0,
        )
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("kid-1")
        time.sleep(1.5)  # the resolver has answered by now
        self.assertEqual(accepted, [], "the expired download opened a connection")
        self.assertEqual(_open_downloads(), 0)


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
