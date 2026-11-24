"""The preview TLS relay only forwards the documented session closure request."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import runpy
import unittest
from pathlib import Path


TLS_RELAY = runpy.run_path(str(Path(__file__).resolve().parents[1] / "preview" / "session_tls.py"))
RELAY_TARGETS = TLS_RELAY["RELAY_TARGETS"]
relay_handler = TLS_RELAY["relay_handler"]


class SessionRelayTest(unittest.TestCase):
    def test_only_session_revocation_is_forwarded(self):
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
        self.assertEqual(RELAY_TARGETS["keycloak"], {
            ("POST", "/realms/platform/protocol/openid-connect/token"),
            ("GET", "/realms/platform/protocol/openid-connect/certs"),
        })

    def test_session_relay_also_forwards_the_two_login_reads(self):
        """The tenant reaches identity-sync through this relay. The login reads use the same origin (AJA-459)."""
        self.assertEqual(RELAY_TARGETS["sessions"], {
            ("POST", "/v1/sessions/revoke"),
            ("GET", "/v1/login-providers"),
            ("POST", "/v1/linked-accounts"),
        })

    def test_setup_script_finds_python_in_both_identity_sync_images(self):
        """The merge preview image has env/bin/python. The local stack image has only python on PATH."""
        script = (Path(__file__).resolve().parents[1] / "preview" / "session-tls.sh").read_text()
        self.assertRegex(script, r"sync_python=")
        self.assertNotRegex(script, r'exec(?: -d)? "\$sync" env/bin/python')
        self.assertIn('"$sync_python"', script)

