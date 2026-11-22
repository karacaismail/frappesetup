"""Gap backlog item 9 (G-13): the key download uses HTTPS only and never follows a redirect.

Plain HTTP is allowed only for a development address: `localhost`, a name under `.localhost`
(RFC 6761 keeps these names off the public DNS) or a loopback IP address.
"""

import gc
import http.server
import json
import threading
import unittest
import warnings

from anahtarlar import Anahtar, jwks

from oidc_verify import JwksCache, JwksUnavailable


class SchemeTest(unittest.TestCase):
    def test_https_is_accepted(self):
        JwksCache("https://idp.example.test/realms/platform/protocol/openid-connect/certs")

    def test_plain_http_to_a_public_name_is_refused(self):
        for url in (
            "http://idp.example.test/certs",
            "http://localhost.example.test/certs",
            "http://kimlik.localhost.example.com/certs",
            "http://10.0.0.5/certs",
            "http://[2001:db8::1]/certs",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                JwksCache(url)

    def test_plain_http_to_a_development_address_is_allowed(self):
        for url in (
            "http://localhost:8080/certs",
            "http://kimlik.localhost:5070/realms/platform/protocol/openid-connect/certs",
            "http://127.0.0.1:5070/certs",
            "http://[::1]:5070/certs",
        ):
            with self.subTest(url=url):
                JwksCache(url)

    def test_other_schemes_are_refused(self):
        for url in ("file:///etc/passwd", "ftp://idp.example.test/certs", "idp.example.test/certs"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                JwksCache(url)


class _Handler(http.server.BaseHTTPRequestHandler):
    body = b""
    paths: list = []

    def do_GET(self):
        type(self).paths.append(self.path)
        if self.path == "/missing":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/certs")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


class RedirectTest(unittest.TestCase):
    def setUp(self):
        self.key = Anahtar("k1")
        handler = type("Handler", (_Handler,), {"body": json.dumps(jwks(self.key)).encode(), "paths": []})
        self.handler = handler
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_direct_download_works(self):
        cache = JwksCache(f"{self.base}/certs", min_refresh_seconds=0)
        self.assertIsNotNone(cache.get_signing_key("k1"))

    def test_refused_redirect_and_http_error_close_their_sockets(self):
        # Third review: an unclosed socket warning appeared in the test run.
        for path in ("/redirect", "/missing"):
            with self.subTest(path=path), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                cache = JwksCache(f"{self.base}{path}", min_refresh_seconds=0)
                with self.assertRaises(JwksUnavailable):
                    cache.get_signing_key("k1")
                del cache
                gc.collect()
                leaked = [w for w in caught if issubclass(w.category, ResourceWarning)]
                self.assertEqual(leaked, [], [str(w.message) for w in leaked])

    def test_redirect_is_not_followed(self):
        cache = JwksCache(f"{self.base}/redirect", min_refresh_seconds=0)
        with self.assertRaises(JwksUnavailable):
            cache.get_signing_key("k1")
        self.assertEqual(self.handler.paths, ["/redirect"])


if __name__ == "__main__":
    unittest.main()
