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


if __name__ == "__main__":
    unittest.main()
