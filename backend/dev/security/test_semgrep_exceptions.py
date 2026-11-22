import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from semgrep_exceptions import CONFIG, RULES, reviewed_findings, source_digest


class SemgrepExceptionsTests(unittest.TestCase):
    def git(self, root, *arguments):
        subprocess.run([shutil.which("git"), "-C", str(root), *arguments], check=True)

    def run_cli(self, root, *arguments):
        script = CONFIG.with_name("semgrep_exceptions.py")
        return subprocess.run(
            [sys.executable, "-B", str(script), *arguments], cwd=root,
            capture_output=True, text=True, check=False,
        )

    def test_cli_snapshot_prints_the_current_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scope = json.loads(CONFIG.read_text())["scope"]
            source = root / scope
            source.mkdir(parents=True)
            (source / "api.py").write_text("pass\n")
            rules = root / RULES
            rules.parent.mkdir(parents=True)
            rules.write_text("rules: []")
            self.git(root, "init", "-q")
            expected = source_digest(root, scope)
            self.assertIsNotNone(expected)
            result = self.run_cli(root, "--snapshot")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected + "\n", ""))

    def test_cli_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.json"
            report.write_text('{"results": [')
            result = self.run_cli(root, str(report), "0", "snapshot")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "Invalid Semgrep review input: JSONDecodeError\n")

    def test_cli_rejects_inconsistent_scan_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.json"
            report.write_text('{"errors": [], "results": []}')
            result = self.run_cli(root, str(report), "1", "snapshot")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "Semgrep did not complete cleanly: exit=1, errors=0, findings=0.\n",
            )

    def test_cli_rejects_scanner_errors_without_dumping_report_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.json"
            scanner_report = {
                "errors": [{"message": "Untrusted scanner text"}],
                "results": [{"extra": {"message": "Untrusted finding text"}}],
            }
            report.write_text(json.dumps(scanner_report))
            result = self.run_cli(root, str(report), "2", "snapshot")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "Semgrep did not complete cleanly: exit=2, errors=1, findings=1.\n",
            )

    def test_digest_ignores_cache_and_preserves_clean_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".gitignore").write_text(".ruff_cache/\n")
            source = root / "press"
            source.mkdir()
            content = b"def endpoint(): pass\n"
            (source / "api.py").write_bytes(content)
            rule_file = root / RULES
            rule_file.parent.mkdir(parents=True)
            rule_file.write_bytes(b"rules: []")
            self.git(root, "init", "-q")
            self.git(root, "add", "press/api.py")

            expected = hashlib.sha256(hashlib.sha256(b"rules: []").digest())
            expected.update(b"press/api.py\0" + hashlib.sha256(content).digest())
            self.assertEqual(source_digest(root, "press"), expected.hexdigest())
            cache = source / ".ruff_cache"
            cache.mkdir()
            (cache / "entry").write_bytes(b"ignored")
            self.assertEqual(source_digest(root, "press"), expected.hexdigest())

    def test_only_exact_reviewed_finding_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "press"
            source.mkdir()
            (source / "api.py").write_text("def endpoint():\n    return 1\n")
            rule_file = root / RULES
            rule_file.parent.mkdir(parents=True)
            rule_file.write_text("rules: []")
            self.git(root, "init", "-q")
            before = source_digest(root, "press")
            config = root / "exceptions.json"
            config.write_text(json.dumps({
                "scope": "press",
                "sha256": before,
                "findings": [{"rule": "frappe-missing-permission", "path": "press/api.py",
                              "line": 1, "reason": "Reviewed permission check."}],
            }))
            finding = {"check_id": "rules.frappe-missing-permission", "path": "press/api.py",
                       "start": {"line": 1}}
            other = {**finding, "start": {"line": 2}}
            self.assertEqual(reviewed_findings(root, config, [finding, other], before), [other])
            self.assertEqual(reviewed_findings(root, config, [finding], "different"), [finding])
            self.assertEqual(reviewed_findings(root, config, [finding], None), [finding])
            rule_file.write_text("rules: changed")
            self.assertEqual(reviewed_findings(root, config, [finding], before), [finding])
            rule_file.write_text("rules: []")
            (source / "guard.py").write_text("guard = False\n")
            self.assertEqual(reviewed_findings(root, config, [finding, other], before), [finding, other])
