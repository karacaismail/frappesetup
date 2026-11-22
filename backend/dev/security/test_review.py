import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scans


class ReviewTests(unittest.TestCase):
    def test_dirty_record_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(scans, "source_state", return_value={"commit": "a", "dirty": True}):
                scans.save(root, "full", [scans.Result("Bandit", "1", "bandit", "pass")])
                self.assertEqual(next(scans.load_results(root)).status, "not_run")

    def test_incomplete_record_renders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "full.json").write_text('{"dirty": false}')
            self.assertIn("not_run", scans.report(root))

    def test_invalid_target_preserves_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(scans, "RESULTS", root):
                scans.save(root, "local", [])
                old = (root / "local.json").read_bytes()
                with self.assertRaises(ValueError):
                    scans.scan_local("http://example.invalid")
                self.assertEqual((root / "local.json").read_bytes(), old)

    def test_all_tracked_backend_manifests(self):
        candidates = "backend/services/new/pyproject.toml\0site/pyproject.toml\0"
        with patch.object(scans, "git", return_value=candidates):
            self.assertEqual(scans.python_manifests(), ["backend/services/new/pyproject.toml"])

    def test_changed_lock_body_fails_reproducibility_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / scans.SECURITY / "requirements.txt"
            lock.parent.mkdir(parents=True)
            lock.write_text("# Manifest SHA256: current\nexample==1\n")
            with patch.object(scans, "ROOT", root), patch.object(scans, "manifest_digest", return_value="current"), \
                    patch.object(scans, "python_manifests", return_value=[]), patch.object(scans, "generated_lock", create=True, return_value="# Manifest SHA256: current\nexample==2\n"):
                with self.assertRaisesRegex(ValueError, "differs"):
                    scans.verify_python_lock([str(lock.relative_to(root))], reproduce=True)
            self.assertIn("example==1", lock.read_text())

    def test_missed_bandit_fixture_fails(self):
        with patch.object(scans, "bandit_findings", return_value=[]), patch.object(scans, "git") as git:
            self.assertEqual(scans.scan_bandit().status, "fail")
            git.assert_not_called()

    def test_unused_bandit_exception_fails(self):
        entry = '{"rule":"B603","file":"backend/a.py","line":1,"owner":"dev","reason":"Fixed argv","ignoreUntil":"2100-01-01"}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / scans.SECURITY / "bandit-exceptions.json"
            config.parent.mkdir(parents=True)
            config.write_text(f"[{entry}]")
            (root / "backend/a.py").touch()
            fixture = [{"test_id": "B101", "line_number": 1}]
            with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value="backend/a.py\0"), \
                    patch.object(scans, "bandit_findings", side_effect=[fixture, []]):
                result = scans.scan_bandit()
            self.assertEqual(result.status, "fail")
            self.assertIn("Unused exception", result.findings[0])

    def test_bad_dependency_prerequisites_fail_before_scanning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / scans.SECURITY / "requirements.txt"
            lock.parent.mkdir(parents=True)
            config = root / scans.OSV_CONFIG
            cache = root / "cache"
            database = cache / "osv-scalibr/PyPI/all.zip"
            database.parent.mkdir(parents=True)
            version = f"osv-scanner version: {scans.OSV}\n"
            with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value=str(lock.relative_to(root))), \
                    patch.object(scans.subprocess, "check_output", return_value=version), \
                    patch.object(scans, "manifest_digest", return_value="current"), patch.object(scans, "run_json") as scan, \
                    patch.dict(os.environ, {"OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY": str(cache)}):
                cases = (
                    ("stale lock", "# Manifest SHA256: old", "", "fresh"),
                    ("bad exception", "# Manifest SHA256: current", "[[IgnoredVulns]]\nid = \"invalid\"", "fresh"),
                    ("missing database", "# Manifest SHA256: current", "", "missing"),
                    ("old database", "# Manifest SHA256: current", "", "old"),
                )
                for name, header, settings, database_state in cases:
                    with self.subTest(name=name):
                        lock.write_text(header)
                        config.write_text(settings)
                        database.unlink(missing_ok=True)
                        if database_state != "missing":
                            database.touch()
                        if database_state == "old":
                            os.utime(database, (1, 1))
                        self.assertEqual(scans.scan_dependencies().status, "fail")
                        scan.assert_not_called()

    def test_gate_requires_merge_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "backend/dev/bin"
            bin_dir.mkdir(parents=True)
            tools = root / "tools"
            tools.mkdir()
            shutil.copy(scans.ROOT / "backend/dev/bin/guvenlik-denetimi", bin_dir)
            security = root / scans.SECURITY
            security.mkdir()
            for name in ("container-settings", "tool-versions.env"):
                shutil.copy(scans.ROOT / scans.SECURITY / name, security)
            for destination, body in {
                tools / "git": 'case "$1" in merge-base) [ -n "$BASE" ] && printf "%s\\n" "$BASE";; esac',
                tools / "uvx": "exit 0",
                tools / "python3": "exit 0",
                tools / "docker": "cat >/dev/null",
                security / "history-scan": "exit 0",
                bin_dir / "ai-readiness": 'printf "%s\\n" "$*" >> "$CALLS"',
            }.items():
                destination.write_text(f"#!/bin/sh\n{body}\n")
                destination.chmod(0o755)
            calls = root / "calls"
            env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "CALLS": str(calls)}
            for base, code, expected in (("abc", 0, ["--self-test", "--commit-base abc"]), ("", 1, ["--self-test"])):
                with self.subTest(base=base):
                    calls.write_text("")
                    result = subprocess.run([bin_dir / "guvenlik-denetimi"], env={**env, "BASE": base},
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(calls.read_text().splitlines(), expected)

    def test_handoff_describes_database_timestamp_limit(self):
        handoff = (scans.ROOT / "backend/docs/handoff/ci-security.md").read_text()
        self.assertIn("dosyanın değişiklik zamanı", handoff)

    def test_decision_lists_exceptions_and_lock_scope(self):
        decision = (scans.ROOT / "backend/docs/kararlar/0011-security-tooling.md").read_text()
        for text in ("bandit-exceptions.json", ".gitleaksignore", "isteğe bağlı paketleri"):
            self.assertIn(text, decision)

    def test_expiry_is_recorded(self):
        record = (scans.ROOT / "backend/PROJE-KAYDI.md").read_text()
        self.assertIn("Bandit istisnaları 22 Şubat 2027 Pazartesi günü", record)

    def test_cli_reports_in_english(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIn("# Security scan results", scans.report(root))
            self.assertIn("# Security scorecard", scans.scorecard(root))


    def test_zap_import_runs_without_network_or_replay(self):
        with patch.object(scans, "run") as runner, patch.dict(os.environ, {"FS_COLIMA_PROFILE": "factory"}):
            scans.scan_zap("http://dev.localhost:8080/", 302, "Found",
                           [("Location", "https://example.invalid/")], b"")
        name, version, command = runner.call_args.args
        self.assertEqual(name, "ZAP passive scan")
        self.assertEqual(command[:3], ["docker", "--context", "colima-factory"])
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("--pull", command)
        self.assertTrue(any(x.startswith(f"ghcr.io/zaproxy/zaproxy:{version}@sha256:") for x in command))
        with tarfile.open(fileobj=io.BytesIO(runner.call_args.kwargs["input_data"])) as archive:
            plan = json.load(archive.extractfile("plan.yaml"))
            har = json.load(archive.extractfile("response.har"))
        self.assertEqual([job["type"] for job in plan["jobs"]], ["import", "passiveScan-wait", "exitStatus"])
        self.assertIs(plan["jobs"][0]["parameters"]["sendRequests"], False)
        self.assertEqual(har["log"]["entries"][0]["request"]["url"], "http://dev.localhost:8080/")
