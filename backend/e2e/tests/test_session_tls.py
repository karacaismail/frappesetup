"""The preview TLS relay only forwards the documented session closure request."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest


class SessionRelayTest(unittest.TestCase):
    def test_only_session_revocation_is_forwarded(self):
        from backend.e2e.preview.session_tls import RELAY_TARGETS, relay_handler

        received = []

        class IdentitySync(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.rfile.read(int(self.headers["Content-Length"])), self.headers["Authorization"]))
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), IdentitySync)
        relay = ThreadingHTTPServer(("127.0.0.1", 0), relay_handler("127.0.0.1", upstream.server_port, RELAY_TARGETS["sessions"]))
        for service in (upstream, relay):
            threading.Thread(target=service.serve_forever, daemon=True).start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", relay.server_port, timeout=3)
            try:
                connection.request("POST", "/wrong", b"{}")
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 404)
                connection.request("POST", "/v1/sessions/revoke", b"{}", {
                    "Authorization": "Bearer only-for-test", "Content-Type": "application/json",
                })
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 202)
                self.assertEqual(received, [("/v1/sessions/revoke", b"{}", "Bearer only-for-test")])
            finally:
                connection.close()
        finally:
            for service in (relay, upstream):
                service.shutdown()
                service.server_close()


    def test_keycloak_relay_allows_only_the_token_and_signing_keys(self):
        from backend.e2e.preview.session_tls import RELAY_TARGETS
        self.assertEqual(RELAY_TARGETS["keycloak"], {
            ("POST", "/realms/platform/protocol/openid-connect/token"),
            ("GET", "/realms/platform/protocol/openid-connect/certs"),
        })
