"""Check the HRMS TR contract runner without Docker or a Frappe site."""

import http.client
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract  # noqa: E402


class Echo(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        body = f"{self.headers['Host']} {self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def fake_compose(directory, script):
    path = Path(directory) / "compose"
    path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    path.chmod(0o700)
    return [str(path)]


class RelayTest(unittest.TestCase):
    def test_relay_forwards_requests_into_the_web_container(self):
        with tempfile.TemporaryDirectory() as directory, HTTPServer(("127.0.0.1", 0), Echo) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            # Arguments: exec -T web env/bin/python -u -c RELAY. Run RELAY with this Python.
            prefix = fake_compose(
                directory,
                f'test "$1 $2 $3" = "exec -T web" || exit 9\n'
                f'FS_TENANT_WEB_PORT={server.server_port} exec "{sys.executable}" -u -c "$7"',
            )
            try:
                with contract.Relay(prefix) as relay:
                    connection = http.client.HTTPConnection("127.0.0.1", relay.port, timeout=10)
                    for path in ("/api/method/ping", "/api/second"):
                        connection.request("GET", path, headers={"Host": "test-hrms-tr.localhost:1"})
                        with connection.getresponse() as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.read().decode(), f"test-hrms-tr.localhost:1 {path}")
                    connection.close()
            finally:
                server.shutdown()
                thread.join()


class CredentialsTest(unittest.TestCase):
    def test_password_comes_from_the_container_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = fake_compose(
                directory,
                'case "$4" in\n'
                '  cat) printf \'{"users": {"employee": "hrms-tr-employee@example.test"}}\' ;;\n'
                '  printenv) test "$5" = HRT_TEST_PASSWORD && echo fabricated-pass ;;\n'
                "  *) exit 9 ;;\n"
                "esac",
            )
            self.assertEqual(
                contract.employee_credentials(prefix, "manifest.json"),
                ("hrms-tr-employee@example.test", "fabricated-pass"),
            )

    def test_missing_password_stops_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = fake_compose(
                directory,
                'test "$4" = cat && printf \'{"users": {"employee": "e@example.test"}}\'\nexit 0',
            )
            with self.assertRaises(ValueError):
                contract.employee_credentials(prefix, "manifest.json")

    def test_failed_compose_returns_a_tool_error(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = fake_compose(directory, "exit 1")
            self.assertEqual(
                contract.main(
                    ["--site", "test-hrms-tr.localhost", "--compose", prefix[0], "--mode", "employee"]
                ),
                2,
            )


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[3])
    unittest.main()
