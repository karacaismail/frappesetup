import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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


if __name__ == "__main__":
    unittest.main()
