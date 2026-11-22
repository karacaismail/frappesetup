"""Exercise credential boundaries using loopback HTTP servers."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import runpy
from secrets import token_urlsafe
import threading
import unittest


request = runpy.run_path(str(Path(__file__).resolve().parents[1] / "keycloak_delivery.py"))["request"]


class DeliveryRequestTest(unittest.TestCase):
    def serve(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def test_does_not_forward_bearer_to_redirect_target(self):
        received = []
        initial = []

        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_args):
                pass

        destination = self.serve(Destination)

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                initial.append(self.headers.get("Authorization"))
                self.send_response(302)
                self.send_header("Location", destination + "/unexpected")
                self.end_headers()

            def log_message(self, *_args):
                pass

        origin = self.serve(Redirect)
        token = token_urlsafe(16)
        status, _, _ = request(origin, "/users", token=token)

        self.assertEqual(initial, ["Bearer " + token])
        self.assertEqual(received, [])
        self.assertEqual(status, 302)

    def test_only_service_relative_paths_and_http_origins_are_allowed(self):
        for path in ("http://foreign.invalid/users", "//foreign.invalid/users", "/users#fragment"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "service-relative"):
                request("http://127.0.0.1:1", path)
        for origin in ("file:///tmp", "https://user@example.invalid", "https://example.invalid/?redirect"):
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, "service address"):
                request(origin, "/users")
