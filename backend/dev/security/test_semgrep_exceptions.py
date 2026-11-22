import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from semgrep_exceptions import CONFIG, RULES, review_scopes, reviewed_findings, source_digest


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
            review = json.loads(CONFIG.read_text())
            scope = review["scope"]
            files = review.get("files")
            for filename in files or [f"{scope}/api.py"]:
                source = root / filename
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("pass\n")
            rules = root / RULES
            rules.parent.mkdir(parents=True, exist_ok=True)
            rules.write_text("rules: []")
            self.git(root, "init", "-q")
            expected = source_digest(root, scope, files)
            self.assertIsNotNone(expected)
            result = self.run_cli(root, "--snapshot")
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            self.assertEqual(json.loads(result.stdout)[scope], expected)

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

    def test_reviews_keep_independent_scopes_and_require_both_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rules = root / RULES
            rules.parent.mkdir(parents=True)
            rules.write_text("rules: []")
            self.git(root, "init", "-q")
            reviews = []
            findings = []
            for scope in ("press", "access"):
                path = f"{scope}/api.py"
                (root / scope).mkdir()
                (root / path).write_text("pass\n")
                reviews.append({
                    "scope": scope, "sha256": source_digest(root, scope),
                    "findings": [{"rule": "frappe-missing-permission", "path": path,
                                  "line": 1, "reason": "Reviewed permission check."}],
                })
                findings.append({"check_id": "rules.frappe-missing-permission", "path": path,
                                 "start": {"line": 1}})
            config = root / "exceptions.json"
            config.write_text(json.dumps({**reviews[0], "additionalReviews": reviews[1:]}))
            before = {entry["scope"]: entry["sha256"] for entry in reviews}
            self.assertEqual(reviewed_findings(root, config, findings, before), [])
            self.assertEqual(reviewed_findings(root, config, findings, {"press": before["press"]}),
                             [findings[1]])
            (root / "access/api.py").write_text("changed = True\n")
            self.assertEqual(reviewed_findings(root, config, findings, before), [findings[1]])

    def test_overlapping_review_targets_are_rejected(self):
        press = {"scope": "backend/apps/press", "findings": []}
        access = {"scope": "backend/apps/core", "files": ["backend/apps/core/allowed.py"], "findings": []}
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "exceptions.json"
            for extra in (
                [{"scope": "backend/apps", "findings": []}],
                [access, {"scope": "backend/apps", "files": ["backend/apps/core/allowed.py"], "findings": []}],
            ):
                with self.subTest(extra=extra):
                    config.write_text(json.dumps({**press, "additionalReviews": extra}))
                    with self.assertRaisesRegex(ValueError, "overlap"):
                        review_scopes(config)

    def test_file_scope_ignores_unrelated_files_and_invalidates_on_helper_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = ["core/endpoint.py", "core/helper.py"]
            unrelated = root / "core/unrelated.py"
            rules = root / RULES
            rules.parent.mkdir(parents=True)
            rules.write_text("rules: []")
            unrelated.parent.mkdir()
            for path in [*(root / file for file in files), unrelated]:
                path.write_text("pass\n")
            self.git(root, "init", "-q")
            self.git(root, "add", "core")
            before = source_digest(root, "core", files)
            config = root / "exceptions.json"
            entry = {"rule": "frappe-missing-permission", "path": files[0], "line": 1,
                     "reason": "Reviewed permission check."}
            config.write_text(json.dumps({
                "scope": "core", "files": files, "sha256": before,
                "findings": [entry, {**entry, "path": "core/unrelated.py"}],
            }))
            finding = {"check_id": "rules.frappe-missing-permission",
                       "path": files[0], "start": {"line": 1}}
            other = {**finding, "path": "core/unrelated.py"}
            unrelated.write_text("changed = True\n")
            self.assertEqual(reviewed_findings(root, config, [finding, other], {"core": before}), [other])
            (root / files[1]).write_text("changed = True\n")
            self.assertEqual(reviewed_findings(root, config, [finding, other], {"core": before}), [finding, other])
            (root / files[1]).unlink()
            self.assertIsNone(source_digest(root, "core", files))

    def test_press_approvals_survive_unrelated_change_but_not_authorization_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = json.loads(CONFIG.read_text())
            scope, files = review["scope"], review["files"]
            press_test = "backend/apps/press_tr/tests/run.sh"
            helpers = (
                "backend/apps/press_tr/press_tr/press_identity/request_policy.py",
                "backend/libs/oidc_verify/src/oidc_verify/verification.py",
            )
            self.assertNotIn(press_test, files)
            self.assertTrue(set(helpers).issubset(files))
            for filename in [*files, press_test, RULES]:
                source = root / filename
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("fixture\n")
            self.git(root, "init", "-q")
            self.git(root, "add", "backend")
            before = source_digest(root, scope, files)
            self.assertIsNotNone(before)
            config = root / "exceptions.json"
            config.write_text(json.dumps({**review, "sha256": before, "additionalReviews": []}))
            findings = [
                {"check_id": entry["rule"], "path": entry["path"], "start": {"line": entry["line"]}}
                for entry in review["findings"]
            ]
            (root / press_test).write_text("changed\n")
            self.assertEqual(reviewed_findings(root, config, findings, {scope: before}), [])
            for filename in helpers:
                with self.subTest(filename=filename):
                    helper = root / filename
                    helper.write_text("changed\n")
                    self.assertEqual(reviewed_findings(root, config, findings, {scope: before}), findings)
                    helper.write_text("fixture\n")

    def test_missing_rule_file_cannot_produce_a_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "press").mkdir()
            self.assertIsNone(source_digest(root, "press"))

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
            before = {"press": source_digest(root, "press")}
            config = root / "exceptions.json"
            config.write_text(json.dumps({
                "scope": "press",
                "sha256": before["press"],
                "findings": [{"rule": "frappe-missing-permission", "path": "press/api.py",
                              "line": 1, "reason": "Reviewed permission check."}],
            }))
            finding = {"check_id": "rules.frappe-missing-permission", "path": "press/api.py",
                       "start": {"line": 1}}
            other = {**finding, "start": {"line": 2}}
            self.assertEqual(reviewed_findings(root, config, [finding, other], before), [other])
            self.assertEqual(reviewed_findings(root, config, [finding], {"press": "different"}), [finding])
            self.assertEqual(reviewed_findings(root, config, [finding], None), [finding])
            rule_file.write_text("rules: changed")
            self.assertEqual(reviewed_findings(root, config, [finding], before), [finding])
            rule_file.write_text("rules: []")
            (source / "guard.py").write_text("guard = False\n")
            self.assertEqual(reviewed_findings(root, config, [finding, other], before), [finding, other])
