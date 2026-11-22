import secrets
import shutil
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
                    with patch.object(scans, "RESULTS", Path(directory)), \
                            patch.object(scans, "scan_zap", return_value=scans.Result("ZAP passive scan", "1", "zap", "pass")), \
                            patch.object(scans, "source_state", return_value={"commit": "a", "dirty": False}):
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
            with patch.object(scans, "source_state", return_value={"commit": "a", "dirty": False}):
                scans.save(path, "full", [scans.Result("Bandit", "1.9.4", "bandit", "fail")])
                scorecard = scans.scorecard(path, open_findings=0, package_vulnerabilities=15)
            self.assertIn("| Open findings | 0 |", scorecard)
            self.assertIn("| Dependency vulnerabilities | 15 |", scorecard)
            self.assertIn("| Rejected requests | Not measured |", scorecard)
            self.assertIn("| Failed checks | 1 |", scorecard)

    def test_report_keeps_skipped_results_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(scans, "source_state", return_value={"commit": "a", "dirty": False}):
                scans.save(path, "full", [scans.Result("Bandit", "1.9.4", "bandit -r backend", "fail")])
                report = scans.report(path)
            self.assertIn("| Bandit | 1.9.4 | `bandit -r backend` | `fail` |", report)
            self.assertIn("`not_run`", report)


class FixtureApi(BaseHTTPRequestHandler):
    """Serve the fixture contract with a configurable answer."""

    answer = 500
    calls = []

    def do_GET(self):
        type(self).calls.append(("GET", self.path, self.headers.get("Host"), self.headers.get("Cookie")))
        body = b'{"message": "ok"}' if type(self).answer == 200 else b'{"error": "boom"}'
        self.send_response(type(self).answer if self.path.startswith("/api/method/fixture.read") else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        type(self).calls.append(("POST", self.path, self.headers.get("Host"), self.headers.get("Cookie")))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        pass


def serve(answer):
    handler = type("Api", (FixtureApi,), {"answer": answer, "calls": []})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread, handler


def stop(server, thread):
    server.shutdown()
    thread.join()
    server.server_close()


class CleanEnvironment(unittest.TestCase):
    """Keep a developer's test user out of these runs."""

    def setUp(self):
        environment = patch.dict(scans.os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("FS_API_TEST_USER", "FS_API_TEST_PASSWORD"):
            scans.os.environ.pop(name, None)


class ContractScanTests(CleanEnvironment):
    fixture = [str(scans.FIXTURES / "contract.yaml")]

    def test_external_contract_targets_are_rejected(self):
        for target in ("http://example.com", "http://10.0.0.1:8000", "http://localhost:8000"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                scans.scan_contracts(target)

    def test_missing_target_is_not_run(self):
        self.assertEqual(scans.scan_contracts(None).status, "not_run")

    def test_closed_site_is_not_run(self):
        with HTTPServer(("127.0.0.1", 0), FixtureApi) as server:
            port = server.server_port
        result = scans.scan_contracts(f"http://dev.localhost:{port}")
        self.assertEqual(result.status, "not_run")
        self.assertEqual(scans.exit_status([result], ci=True), 1)

    def test_command_reads_only_by_default(self):
        command = scans.contract_command("c.yaml", 8001, "config.toml", "report.json")
        self.assertEqual(command[command.index("--include-method") + 1], "GET")
        self.assertIn("--max-redirects", command)
        self.assertIn("schemathesis@" + scans.VERSIONS["SCHEMATHESIS_VERSION"], command)
        self.assertEqual(command[command.index("--origin") + 1], "http://127.0.0.1:8001")
        writes = scans.contract_command("c.yaml", 8001, "config.toml", "report.json", writes=True)
        self.assertNotIn("--include-method", writes)

    def test_version_is_exact(self):
        self.assertRegex(scans.VERSIONS["SCHEMATHESIS_VERSION"], r"^\d+\.\d+\.\d+$")

    def test_administrator_is_refused(self):
        server, thread, _handler = serve(200)
        try:
            with patch.dict(scans.os.environ, {"FS_API_TEST_USER": "Administrator",
                                               "FS_API_TEST_PASSWORD": secrets.token_hex(8)}):
                result = scans.scan_contracts(f"http://127.0.0.1:{server.server_port}",
                                              contracts=self.fixture)
        finally:
            stop(server, thread)
        self.assertEqual(result.status, "fail")

    @unittest.skipUnless(shutil.which("uvx"), "uvx is required for the Schemathesis run.")
    def test_contracts_without_read_operations_are_not_run(self):
        server, thread, _handler = serve(200)
        try:
            with tempfile.TemporaryDirectory() as directory:
                contract = Path(directory) / "writes.yaml"
                contract.write_text('openapi: 3.1.0\ninfo: {title: W, version: "1"}\npaths:\n'
                                    '  /api/method/fixture.write:\n    post:\n'
                                    '      responses: {"200": {description: OK}}\n')
                with patch.object(scans, "contract_fixture_found", return_value=True):
                    result = scans.scan_contracts(f"http://127.0.0.1:{server.server_port}",
                                                  contracts=[str(contract)])
        finally:
            stop(server, thread)
        self.assertEqual(result.status, "not_run")
        self.assertEqual(scans.exit_status([result], ci=True), 1)

    def test_findings_name_contract_check_and_operation(self):
        report = {"complete": True, "errors": [], "failures": [
            {"code": "ST101", "title": "Server error", "operations": ["GET /a", "GET /b"]}]}
        self.assertEqual(scans.contract_findings(report, "backend/contracts/x.yaml"), (
            "backend/contracts/x.yaml · ST101 Server error · GET /a",
            "backend/contracts/x.yaml · ST101 Server error · GET /b"))
        with self.assertRaises(ValueError):
            scans.contract_findings({"complete": False, "errors": [], "failures": []}, "x.yaml")


@unittest.skipUnless(shutil.which("uvx"), "uvx is required for the Schemathesis run.")
class SchemathesisRunTests(CleanEnvironment):
    fixture = [str(scans.FIXTURES / "contract.yaml")]

    def run_against(self, answer, **options):
        server, thread, handler = serve(answer)
        try:
            result = scans.scan_contracts(f"http://dev.localhost:{server.server_port}",
                                          contracts=self.fixture, **options)
        finally:
            stop(server, thread)
        return result, handler.calls

    def test_server_error_fails_and_writes_are_not_sent(self):
        result, calls = self.run_against(500)
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("ST101" in finding and "GET /api/method/fixture.read" in finding
                            for finding in result.findings), result.findings)
        self.assertNotIn("POST", {method for method, *_rest in calls})
        self.assertTrue(all(host.startswith("dev.localhost:") for _method, _path, host, _cookie in calls))

    def test_conforming_site_passes(self):
        result, _calls = self.run_against(200)
        self.assertEqual(result.status, "pass", result.findings)

    def test_session_cookie_comes_from_environment(self):
        server, thread, handler = serve(200)
        try:
            findings = scans.run_contract(self.fixture[0], "dev.localhost", server.server_port,
                                          sid="fixture-sid")
        finally:
            stop(server, thread)
        self.assertEqual(findings[0], ())
        self.assertEqual({cookie for *_rest, cookie in handler.calls}, {"sid=fixture-sid"})

    def test_absolute_and_relative_servers_stay_on_loopback(self):
        for base in ("https://example.com/api/method", "/api/method"):
            server, thread, handler = serve(200)
            try:
                with tempfile.TemporaryDirectory() as directory:
                    contract = Path(directory) / "servers.yaml"
                    contract.write_text(f'openapi: 3.1.0\ninfo: {{title: S, version: "1"}}\n'
                                        f'servers: [{{url: "{base}"}}]\npaths:\n'
                                        '  /fixture.read:\n    get:\n'
                                        '      responses: {"200": {description: OK}}\n')
                    scans.run_contract(str(contract), "dev.localhost", server.server_port)
            finally:
                stop(server, thread)
            paths = {path.split("?")[0] for _method, path, _host, _cookie in handler.calls}
            with self.subTest(base=base):
                self.assertIn("/api/method/fixture.read", paths)

    def test_writes_require_explicit_option(self):
        _result, calls = self.run_against(200, writes=True)
        self.assertIn("POST", {method for method, *_rest in calls})


if __name__ == "__main__":
    unittest.main()
