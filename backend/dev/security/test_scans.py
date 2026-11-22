import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import scans


class SecurityScanTests(unittest.TestCase):
    def test_external_targets_are_rejected(self):
        for target in ("http://example.com", "http://localhost",
                       "http://127.0.0.1@example.com", "http://bad..localhost"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                scans.local_target(target)

    def test_local_virtual_host_is_preserved(self):
        self.assertEqual(scans.local_target("http://dev.localhost:8080"), ("dev.localhost", 8080))

    def test_local_check_does_not_follow_redirects(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path, self.headers["Host"]))
                self.send_response(302)
                self.send_header("Location", "https://example.com/")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            port = server.server_port
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as directory:
                    with patch.object(scans, "RESULTS", Path(directory)):
                        self.assertEqual(scans.scan_local(f"http://dev.localhost:{port}"), 0)
                        self.assertIn("`pass`", scans.report(Path(directory)))
            finally:
                server.shutdown()
                thread.join()

        self.assertEqual(requests, [("/", f"dev.localhost:{port}")])

    def test_report_keeps_skipped_results_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            scans.save(path, "full", [scans.Result("Bandit", "1.9.4", "bandit -r backend", "fail")])
            report = scans.report(path)
            self.assertIn("| Bandit | 1.9.4 | `bandit -r backend` | `fail` |", report)
            self.assertIn("`not_run`", report)


if __name__ == "__main__":
    unittest.main()
