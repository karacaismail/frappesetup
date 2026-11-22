"""The delivery check must send Keycloak credentials only to its configured servers."""

import http.server
import os
import runpy
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "keycloak_delivery.py"
# A fixed fake bearer value. It is not a credential.
FAKE_BEARER = "synthetic"


class Recorder(http.server.BaseHTTPRequestHandler):
    """Record each request. A configured location turns the reply into a redirect."""

    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get("Authorization")))
        if self.server.location:
            self.send_response(302)
            self.send_header("Location", self.server.location)
            self.end_headers()
            return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *args):
        pass


def serve(location=None):
    server = http.server.HTTPServer(("127.0.0.1", 0), Recorder)
    server.seen = []
    server.location = location
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


class KeycloakDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(MODULE))

    def start(self, location=None):
        server, origin = serve(location)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, origin

    def test_allows_a_configured_origin(self):
        server, origin = self.start()
        status, _, body = self.module["request"](origin + "/ok", origins={origin}, token=FAKE_BEARER)
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(server.seen, [("/ok", "Bearer synthetic")])

    def test_rejects_another_server_before_sending(self):
        server, origin = self.start()
        other = origin.rsplit(":", 1)[0].replace("127.0.0.1", "localhost") + ":" + origin.rsplit(":", 1)[1]
        for url in (
            other + "/token",
            "http://127.0.0.1:1/token",
            "file:///etc/passwd",
            "ftp://127.0.0.1/token",
            origin.replace("http://", "https://") + "/token",
            "http://synthetic@" + origin.removeprefix("http://") + "/token",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "not allowed"):
                    self.module["request"](url, origins={origin}, token=FAKE_BEARER)
        self.assertEqual(server.seen, [])

    def test_does_not_follow_redirects_or_forward_credentials(self):
        target, target_origin = self.start()
        for location in (target_origin + "/stolen", "/same-server"):
            with self.subTest(location=location):
                source, origin = self.start(location)
                with self.assertRaisesRegex(ValueError, "redirect"):
                    self.module["request"](
                        origin + "/token", origins={origin, target_origin}, token=FAKE_BEARER
                    )
                self.assertEqual(source.seen, [("/token", "Bearer synthetic")])
        self.assertEqual(target.seen, [])

    def test_ignores_proxy_settings(self):
        proxy, proxy_origin = self.start()
        server, origin = self.start()
        proxies = {name: proxy_origin for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY")}
        with patch.dict(os.environ, {**proxies, "no_proxy": "", "NO_PROXY": ""}):
            module = runpy.run_path(str(MODULE))
            module["request"](origin + "/ok", origins={origin}, token=FAKE_BEARER)
        self.assertEqual(proxy.seen, [])
        self.assertEqual(server.seen, [("/ok", "Bearer synthetic")])

    def test_configured_origin_must_be_http_or_https(self):
        for base in ("file:///tmp", "ftp://keycloak.test", "keycloak.test", "http://user@keycloak.test"):
            with self.subTest(base=base):
                with self.assertRaisesRegex(ValueError, "Keycloak URL"):
                    self.module["origin"](base)

    def test_rejects_an_unexpected_user_location(self):
        for location in ("http://other.test/admin/realms/platform/users/../../master", "", "/users/a/b?x"):
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, "user ID"):
                    self.module["user_id"](location)
        self.assertEqual(
            self.module["user_id"]("http://kc.test/admin/realms/platform/users/0f8fad5b-d9cb-469f-a165-70867728950e"),
            "0f8fad5b-d9cb-469f-a165-70867728950e",
        )


if __name__ == "__main__":
    unittest.main()
