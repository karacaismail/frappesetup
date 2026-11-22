import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from datetime import date
from unittest.mock import patch

import scans


class SecurityScanTests(unittest.TestCase):
    def test_external_targets_are_rejected(self):
        for target in ("http://example.com", "http://localhost",
                       "http://127.0.0.1@example.com", "http://bad..localhost",
                       "http://user@127.0.0.1", "http://:@127.0.0.1",
                       "http://dev.localhost.", "https://127.0.0.1",
                       "http://[::1]", "http://127.1",
                       "http://127.0.0.1:0", "http://127.0.0.1:65536"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                scans.local_target(target)

    def test_local_virtual_host_is_preserved(self):
        self.assertEqual(scans.local_target("http://dev.localhost:8080"), ("dev.localhost", 8080))

    def test_uppercase_local_target(self):
        self.assertEqual(scans.local_target("http://DEV.LOCALHOST"), ("dev.localhost", 80))

    def test_ci_fails_when_required_check_did_not_run(self):
        result = scans.Result("ZAP Baseline", "—", "—", "not_run")
        self.assertEqual(scans.exit_status([result], ci=True), 1)
        self.assertEqual(scans.exit_status([result], ci=False), 0)

    def test_old_and_in_progress_records_do_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(scans, "source_state", return_value={"commit": "one", "dirty": False}):
                scans.save(path, "full", [scans.Result("Bandit", "1", "bandit", "pass")])
            with patch.object(scans, "source_state", return_value={"commit": "two", "dirty": False}):
                self.assertNotIn("`pass`", scans.report(path))
                scans.save(path, "full", [])
                self.assertIn("`not_run`", scans.report(path))

    def test_bandit_exception_requires_owner_and_unexpired_date(self):
        item = {"rule": "B603", "file": "backend/example.py", "line": 2,
                "owner": "dev", "reason": "Fixed argv.", "ignoreUntil": "2026-12-01"}
        self.assertTrue(scans.valid_exception(item, date(2026, 11, 22)))
        self.assertFalse(scans.valid_exception({**item, "owner": ""}, date(2026, 11, 22)))
        self.assertFalse(scans.valid_exception(item, date(2026, 12, 2)))

    def test_dependency_locks_include_root_and_exclude_fixtures(self):
        files = ["package-lock.json", "backend/apps/a/requirements.txt",
                 "backend/dev/security/fixtures/requirements.txt"]
        self.assertEqual(scans.dependency_locks(files), files[:2])

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

    def test_unavailable_site_is_not_run_and_fails_ci(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(scans, "RESULTS", Path(directory)):
                with patch.object(scans.http.client.HTTPConnection, "request", side_effect=ConnectionRefusedError):
                    self.assertEqual(scans.scan_local("http://127.0.0.1:8000", ci=True), 1)
                results = scans.read_record(Path(directory), "local")["results"]
                self.assertEqual([result["status"] for result in results], ["not_run", "not_run"])

    def test_scorecard_distinguishes_zero_from_missing_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            scans.save(path, "full", [scans.Result("Bandit", "1.9.4", "bandit", "fail")])
            scorecard = scans.scorecard(path, open_findings=0, package_vulnerabilities=15)
            self.assertIn("| Açık bulgu | 0 |", scorecard)
            self.assertIn("| Paket açığı | 15 |", scorecard)
            self.assertIn("| Reddedilen istek | Ölçülmedi |", scorecard)
            self.assertIn("| Başarısız denetim | 1 |", scorecard)

    def test_report_keeps_skipped_results_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            scans.save(path, "full", [scans.Result("Bandit", "1.9.4", "bandit -r backend", "fail")])
            report = scans.report(path)
            self.assertIn("| Bandit | 1.9.4 | `bandit -r backend` | `fail` |", report)
            self.assertIn("`not_run`", report)


if __name__ == "__main__":
    unittest.main()
