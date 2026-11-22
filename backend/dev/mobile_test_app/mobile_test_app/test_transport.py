"""Check that both test clients keep requests on the original local endpoint."""

import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from platform_core.api import test_mobile

from . import load_test


class RedirectingEndpoint(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(302)
        self.send_header("Location", "/redirect-target")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self.server.redirect_count += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"followed": true}')

    def log_message(self, *_args):
        pass


class TestMobileHttpTransport(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectingEndpoint)
        self.server.redirect_count = 0
        self.addCleanup(self.server.server_close)
        worker = Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(self.server.shutdown)

    def test_load_client_rejects_redirect(self):
        status, result = load_test.call(self.server.server_port, "Bearer synthetic", "pull", {})
        self.assertEqual((status, result), (302, {"code": "redirect_rejected"}))
        self.assertEqual(self.server.redirect_count, 0)

    def test_http_suite_client_rejects_redirect(self):
        with patch.object(test_mobile, "BASE", f"http://127.0.0.1:{self.server.server_port}"):
            status, result, _unused = test_mobile.MobileHTTPTest().post_method("fixture", {}, "synthetic")
        self.assertEqual((status, result), (302, {"code": "redirect_rejected"}))
        self.assertEqual(self.server.redirect_count, 0)

    def test_http_suite_client_rejects_non_loopback_and_non_http_urls(self):
        for url in ("http://example.test", "ftp://127.0.0.1", "http://user@127.0.0.1", "http://localhost"):
            with (
                self.subTest(url=url),
                patch.object(test_mobile, "BASE", url),
                patch(
                    "socket.create_connection", side_effect=AssertionError("Unexpected connection")
                ) as connect,
            ):
                with self.assertRaisesRegex(ValueError, "loopback"):
                    test_mobile.MobileHTTPTest().post_method("fixture", {}, "synthetic")
                connect.assert_not_called()

    def test_load_client_rejects_an_injected_authority(self):
        with patch("socket.create_connection") as connect:
            with self.assertRaisesRegex(ValueError, "loopback"):
                load_test.call("80@example.test", "Bearer synthetic", "pull", {})
            connect.assert_not_called()
