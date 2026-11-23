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

    def test_bandit_scans_a_tracked_backend_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / scans.SECURITY / "bandit-exceptions.json"
            config.parent.mkdir(parents=True)
            config.write_text("[]")
            target = "backend/known.py"
            (root / target).write_text("assert False\n")
            (root / "backend/untracked.py").write_text("assert False\n")
            script = "backend/python-script"
            direct = "backend/direct-python"
            root_python = "backend/root-python"
            env_long = "backend/env-long-python"
            python_sh = "backend/python-script.sh"
            shell = "backend/shell-script.sh"
            (root / script).write_text("#!/usr/bin/env -S python3.14 -I\nassert False\n")
            (root / direct).write_text("#! /usr/bin/python3\nassert False\n")
            (root / root_python).write_text("#!/python3\n")
            (root / env_long).write_text("#!/usr/bin/env --split-string=python3 -I\n")
            (root / python_sh).write_text("#!/usr/bin/env python3\nassert False\n")
            (root / shell).write_text("#!/bin/sh\n")
            (root / "backend/symlink").symlink_to(script.rsplit("/", 1)[1])
            tracked = "\0".join((target, script, direct, root_python, env_long, python_sh, shell, "backend/symlink", ""))
            fixture = [{"test_id": "B101", "line_number": 1}]
            finding = {**fixture[0], "filename": target}
            with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value=tracked), \
                    patch.object(scans, "bandit_findings", side_effect=[fixture, [finding]]) as scan:
                result = scans.scan_bandit()
            self.assertEqual(scan.call_args.args[1], [target, script, direct, root_python, env_long, python_sh])
            for call in scan.call_args_list:
                self.assertIn("--ignore-nosec", call.args[0])
            self.assertEqual(result.status, "fail")
            self.assertEqual(result.findings, (f"B101 · {target}:1",))

    def test_unused_bandit_exception_fails(self):
        entry = '{"rule":"B603","file":"backend/a.py","code":"run()","statementSha256":"1111111111111111111111111111111111111111111111111111111111111111","owner":"dev","reason":"Fixed argv","ignoreUntil":"2100-01-01"}'
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
            shutil.copy(scans.ROOT / "backend/dev/bin/security-audit", bin_dir)
            security = root / scans.SECURITY
            security.mkdir()
            for name in ("container-settings", "tool-versions.env"):
                shutil.copy(scans.ROOT / scans.SECURITY / name, security)
            for destination, body in {
                tools / "git": 'case "$1" in merge-base) [ -n "$BASE" ] && printf "%s\\n" "$BASE";; esac',
                tools / "uvx": "exit 0",
                tools / "uv": 'printf "%s\\n" "$*" >> "$CALLS"; exit "$BANDIT_STATUS"',
                tools / "python3": "exit 0",
                tools / "docker": "cat >/dev/null",
                security / "history-scan": "exit 0",
                bin_dir / "ai-readiness": 'printf "%s\\n" "$*" >> "$CALLS"',
            }.items():
                destination.write_text(f"#!/bin/sh\n{body}\n")
                destination.chmod(0o755)
            calls = root / "calls"
            env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "CALLS": str(calls)}
            bandit_call = "run --no-project --offline --python 3.12 python -B backend/dev/security/scans.py bandit"
            # The gate also scans the Press lock offline (review 1, finding 3).
            press_lock_call = "run --no-project --offline --python 3.12 python -B backend/dev/security/scans.py press-lock"
            for base, bandit_status, gate_status, remaining in (
                ("abc", 0, 0, ["--self-test", "--commit-base abc"]),
                ("", 0, 1, ["--self-test"]),
                ("abc", 1, 1, ["--self-test", "--commit-base abc"]),
            ):
                with self.subTest(base=base, bandit_status=bandit_status):
                    calls.write_text("")
                    result = subprocess.run([bin_dir / "security-audit"], env={**env, "BASE": base,
                                            "BANDIT_STATUS": str(bandit_status)}, capture_output=True, text=True)
                    self.assertEqual(result.returncode, gate_status, result.stderr)
                    self.assertEqual(calls.read_text().splitlines(), [bandit_call, press_lock_call, *remaining])

    def test_handoff_describes_database_timestamp_limit(self):
        handoff = (scans.ROOT / "backend/docs/handoff/ci-security.md").read_text()
        self.assertIn("dosyanın değişiklik zamanı", handoff)

    def test_decision_lists_exceptions_and_lock_scope(self):
        decision = (scans.ROOT / "backend/docs/decisions/0011-security-tooling.md").read_text()
        for text in ("bandit-exceptions.json", ".gitleaksignore", "isteğe bağlı paketleri"):
            self.assertIn(text, decision)

    def test_security_documents_use_current_paths_and_explain_snapshot(self):
        readme = (scans.ROOT / scans.SECURITY / "README.md").read_text()
        decision = (scans.ROOT / "backend/docs/decisions/0011-security-tooling.md").read_text()
        handoff = (scans.ROOT / "backend/docs/handoff/ci-security.md").read_text()
        for text in ("backend/dev/bin/security-audit", "backend/dev/security/fixtures/",
                     "backend/dev/security/semgrep_exceptions.py --snapshot"):
            self.assertIn(text, readme)
        self.assertIn("`security-audit`", decision)
        self.assertIn("backend/dev/security/semgrep-exceptions.json", decision)
        self.assertIn("backend/dev/bin/tunnel open", handoff)

    def test_access_decision_points_to_the_runtime_scope_list(self):
        record = (scans.ROOT / "backend/PROJECT-RECORD.md").read_text()
        decision = record.split("**O-42.", 1)[1].split("\n\n", 1)[0]
        self.assertIn("backend/dev/security/semgrep-exceptions.json", decision)

    def test_expiry_is_recorded(self):
        record = (scans.ROOT / "backend/PROJECT-RECORD.md").read_text()
        self.assertIn("Bandit istisnaları 22 Şubat 2027 Pazartesi günü", record)

    def test_cli_reports_in_english(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIn("# Security scan results", scans.report(root))
            self.assertIn("# Security scorecard", scans.scorecard(root))


    def test_zap_import_runs_without_network_or_replay(self):
        with patch.object(scans.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, stdout=b'{"site": []}'
        )) as runner, patch.dict(os.environ, {"FS_COLIMA_PROFILE": "factory"}):
            result = scans.scan_zap("http://dev.localhost:8080/", 302, "Found",
                                    [("Location", "https://example.invalid/")], b"")
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.findings, ())
        command, = runner.call_args.args
        version = scans.VERSIONS["ZAP_VERSION"]
        self.assertEqual(command[:3], ["docker", "--context", "colima-factory"])
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("--pull", command)
        self.assertTrue(any(x.startswith(f"ghcr.io/zaproxy/zaproxy:{version}@sha256:") for x in command))
        with tarfile.open(fileobj=io.BytesIO(runner.call_args.kwargs["input"])) as archive:
            plan = json.load(archive.extractfile("plan.yaml"))
            har = json.load(archive.extractfile("response.har"))
        self.assertEqual([job["type"] for job in plan["jobs"]], ["import", "passiveScan-wait", "report", "exitStatus"])
        self.assertIs(plan["jobs"][0]["parameters"]["sendRequests"], False)
        self.assertEqual(plan["jobs"][2]["parameters"]["template"], "traditional-json")
        self.assertEqual(har["log"]["entries"][0]["request"]["url"], "http://dev.localhost:8080/")

    def test_runtime_inventory_requires_exactly_one_image_id(self):
        image = "sha256:" + "1" * 64
        self.assert_script_rejects("runtime-packages", ([], ["latest"], [image, "extra"]),
                                   1, "Use the exact local image ID")

    def test_history_scan_rejects_unknown_or_extra_arguments(self):
        self.assert_script_rejects("history-scan", (["--unknown"], ["--self-test", "extra"]),
                                   2, "Usage: history-scan [--self-test]")

    def assert_script_rejects(self, name, cases, exit_code, message):
        script = scans.ROOT / scans.SECURITY / name
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory)
            docker = tools / "docker"
            docker.write_text("#!/bin/sh\nprintf 'unexpected docker call\\n'\nexit 42\n")
            docker.chmod(0o755)
            env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "FS_COLIMA_PROFILE": "ci"}
            for args in cases:
                with self.subTest(args=args):
                    result = subprocess.run([script, *args], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, exit_code)
                    self.assertIn(message, result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_missing_osv_binary_is_not_run(self):
        # osv_scanner() finds no pinned scanner on PATH or in the osv-setup cache. Patch it, because
        # the machine running the test may have the cached copy.
        with patch.object(scans, "git", return_value="backend/dev/security/requirements.txt"), \
                patch.object(scans, "osv_scanner", return_value=None), \
                patch.object(scans, "verify_python_lock") as verify:
            result = scans.scan_dependencies()
        self.assertEqual(result.status, "not_run")
        verify.assert_not_called()

    def test_full_gate_fails_when_osv_cannot_run(self):
        passed = scans.Result("Other check", "1", "test", "pass")
        missing = scans.Result("OSV-Scanner", scans.OSV, "osv-scanner", "not_run")
        with patch.object(scans, "source_state", return_value={}), patch.object(scans, "save") as save, \
                patch.object(scans, "run", return_value=passed), patch.object(scans, "scan_bandit", return_value=passed), \
                patch.object(scans, "runtime_inventory", return_value=passed), \
                patch.object(scans, "scan_contracts", return_value=passed), \
                patch.object(scans, "scan_dependencies", return_value=missing):
            for ci in (False, True):
                with self.subTest(ci=ci):
                    self.assertEqual(scans.scan_full(None, ci=ci), 1)
                    self.assertIn(missing, save.call_args.args[2])

    def test_offline_osv_reports_git_dependencies_as_unchecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = scans.SECURITY / "requirements.txt"
            (root / lock.parent).mkdir(parents=True)
            (root / lock).write_text(
                "regular==1.0\n"
                "pypika @ git+https://example.test/upstream/pypika@abcdef\n"
            )
            fixture = {"results": [{"packages": [{"vulnerabilities": [{"id": "GHSA-hmr4-m2h5-33qx"}]}]}]}
            version = f"osv-scanner version: {scans.OSV}\n"
            with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value=str(lock)), \
                    patch.object(scans.subprocess, "check_output", return_value=version), \
                    patch.object(scans, "verify_python_lock"), patch.object(scans, "validate_osv_inputs"), \
                    patch.object(scans, "run_json", side_effect=[(1, fixture), (0, {"results": []})]):
                result = scans.scan_dependencies()
            self.assertEqual(result.status, "pass")
            self.assertEqual(result.findings, (f"not_run · {lock} · pypika · Git dependency outside offline OSV scan",))

    def test_zap_reports_only_alert_id_risk_and_local_address(self):
        url = "http://dev.localhost:8080/"
        alert = {"pluginid": "10020", "alertRef": "10020-1", "riskcode": "2",
                 "instances": [
                     {"uri": url, "evidence": "sid=fake-cookie"},
                     {"uri": url + "?secret=ignore-this"},
                     {"uri": "http://other.localhost:8080/"},
                     {"uri": url},
                 ]}
        report = {"site": [{"alerts": [alert]}]}
        process = subprocess.CompletedProcess([], 1, stdout=json.dumps(report), stderr="raw diagnostics")
        with patch.object(scans.subprocess, "run", return_value=process), patch("sys.stdout", new_callable=io.StringIO) as output:
            result = scans.scan_zap(url, 200, "OK", [], b"")
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.findings, (f"10020-1 · Medium · {url}",))
        self.assertIn(f"ZAP: 10020-1 · Medium · {url}", output.getvalue())
        for unwanted in ("fake-cookie", "ignore-this", "other.localhost", "raw diagnostics"):
            self.assertNotIn(unwanted, output.getvalue())

    def test_zap_rejects_missing_or_invalid_json_report(self):
        for stdout in ("", "raw response", '{"site": null}', "{}"):
            with self.subTest(stdout=stdout), patch.object(scans.subprocess, "run", return_value=
                    subprocess.CompletedProcess([], 0, stdout=stdout, stderr="sid=fake-cookie")), \
                    patch("sys.stdout", new_callable=io.StringIO) as output:
                result = scans.scan_zap("http://127.0.0.1:8080/", 200, "OK", [], b"")
                self.assertEqual(result.status, "fail")
                self.assertNotIn("fake-cookie", output.getvalue())
