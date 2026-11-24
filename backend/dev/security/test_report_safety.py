import ast
import hashlib
import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
import scans


class ReportSafetyTests(unittest.TestCase):
    def test_markdown_rendering_preserves_literal_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scans.Result(
                "Bandit | sample\n## fake heading", "1|2", "`sample | value`", "fail",
                findings=("**literal** <sample>\n# fake heading",),
            )
            state = {"commit": "a", "branch": "edge``case", "dirty": False}
            with patch.object(scans, "source_state", return_value=state):
                scans.save(root, "full", [result])
                report = scans.report(root)
            for unwanted in ("\n## fake heading", "\n# fake heading", "**literal**", "<sample>", "Bandit | sample", "1|2"):
                self.assertNotIn(unwanted, report)
            self.assertIn("``` edge``case ```", report)

    def test_bandit_config_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / scans.SECURITY / "bandit-exceptions.json"
            config.parent.mkdir(parents=True)
            config.write_text('[{"rule":"B603","file":"backend/a.py","line":1,"owner":"first","owner":"second",'
                              '"reason":"Local test","ignoreUntil":"2100-01-01"}]')
            (root / "backend/a.py").touch()
            fixture = [{"test_id": "B101", "line_number": 1}]
            finding = {"test_id": "B603", "line_number": 1, "filename": "backend/a.py"}
            with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value="backend/a.py\0"), \
                    patch.object(scans, "bandit_findings", side_effect=[fixture, [finding]]) as bandit:
                self.assertEqual(scans.scan_bandit().status, "fail")
                self.assertEqual(bandit.call_count, 1)


    def test_bandit_exception_moves_with_code_and_fails_for_changed_or_duplicate_code(self):
        original = 'run(\n    "reviewed",\n)'
        signature = hashlib.sha256(("\n" + original).encode()).hexdigest()
        entry = {"rule": "B603", "file": "backend/a.py", "code": "run(",
                 "statementSha256": signature, "owner": "dev", "reason": "Reviewed test command",
                 "ignoreUntil": "2100-01-01"}
        fixture = [{"test_id": "B101", "line_number": 1}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / scans.SECURITY / "bandit-exceptions.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps([entry]))
            source = root / "backend/a.py"
            for content, lines, expected in (
                (original, [1], "pass"),
                ("\n\n" + original, [3], "pass"),
                (original.replace("reviewed", "changed"), [1], "fail"),
                (original + "\n" + original, [1, 4], "fail"),
                (original, [1, 1], "fail"),
            ):
                with self.subTest(lines=lines, expected=expected):
                    source.write_text(content)
                    findings = [{"test_id": "B603", "line_number": line, "filename": "backend/a.py"}
                                for line in lines]
                    with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value="backend/a.py\0"), \
                            patch.object(scans, "bandit_findings", side_effect=[fixture, findings]):
                        result = scans.scan_bandit()
                    self.assertEqual(result.status, expected)
                    if expected == "fail":
                        self.assertIn("Unused exception", " ".join(result.findings))
                        self.assertIn("B603 · backend/a.py:1", result.findings)

    def test_bandit_exception_requires_exact_reviewed_count(self):
        source_text = 'example = {"password": "fixture", "secret": "fixture"}'
        code, digest = scans.bandit_source_signature(source_text, ast.parse(source_text), 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / scans.SECURITY / "bandit-exceptions.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps([{
                "rule": "B105", "file": "backend/a.py", "code": code, "statementSha256": digest,
                "owner": "dev", "reason": "Two fixture fields", "ignoreUntil": "2100-01-01",
                "occurrences": 2,
            }]))
            source = root / "backend/a.py"
            finding = {"test_id": "B105", "line_number": 1, "filename": "backend/a.py"}
            for lines, content, expected in (
                ([1, 1], source_text, "pass"),
                ([1], source_text, "fail"),
                ([1, 1, 1], source_text, "fail"),
                ([1, 2], f"{source_text}\n{source_text}", "pass"),
                ([1, 1], source_text.replace("fixture", "changed"), "fail"),
            ):
                with self.subTest(lines=lines, content=content):
                    source.write_text(content)
                    findings = [dict(finding, line_number=line) for line in lines]
                    with patch.object(scans, "ROOT", root), patch.object(scans, "git", return_value="backend/a.py\0"), \
                            patch.object(scans, "bandit_findings", side_effect=[[{"test_id": "B101", "line_number": 1}], findings]):
                        self.assertEqual(scans.scan_bandit().status, expected)


        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "full.json").write_text('{"dirty": [], "results": []}')
            self.assertIn("Working tree: unknown.", scans.report(root))

    def test_missing_contract_report_discards_raw_tool_output(self):
        contract = "backend/contracts/example.yaml"
        email = "fake-person@example.test"
        cookie = "sid=fake-session; alternate=fake-cookie"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            output = io.StringIO()
            with patch.object(scans.http.client, "HTTPConnection"), patch.object(scans, "contract_session", return_value=None), \
                    patch.object(scans, "contract_fixture_found", return_value=True), \
                    patch.object(scans.subprocess, "run", return_value=Mock(stdout=email, stderr=cookie, returncode=2)), redirect_stdout(output):
                result = scans.scan_contracts("http://127.0.0.1:1234", contracts=[contract])
            scans.save(path, "full", [result])
            self.assertEqual(result.status, "fail")
            self.assertIn(f"CONTRACT_REPORT_UNAVAILABLE {contract}", output.getvalue())
            for value in (email, "fake-session", "fake-cookie"):
                self.assertNotIn(value, output.getvalue())
                self.assertNotIn(value, (path / "full.json").read_text())

    def test_contract_summary_separates_coverage_from_authorization(self):
        output = io.StringIO()
        with patch.object(scans.http.client, "HTTPConnection"), patch.object(scans, "contract_session", return_value=None), \
                patch.object(scans, "contract_fixture_found", return_value=True), \
                patch.object(scans, "run_contract", return_value=((), 3)), redirect_stdout(output):
            result = scans.scan_contracts("http://127.0.0.1:1234", contracts=["backend/contracts/example.yaml"])
        self.assertEqual(result.status, "pass")
        self.assertIn("3 operations tested (GET only)", output.getvalue())
        self.assertIn("Authorization requires separate role tests.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
