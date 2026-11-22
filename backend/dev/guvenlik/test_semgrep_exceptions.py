import json
import tempfile
import unittest
from pathlib import Path

from semgrep_exceptions import RULES, reviewed_findings, source_digest


class SemgrepExceptionsTests(unittest.TestCase):
    def test_only_exact_reviewed_finding_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "press"
            source.mkdir()
            (source / "api.py").write_text("def endpoint():\n    return 1\n")
            rule_file = root / RULES
            rule_file.parent.mkdir(parents=True)
            rule_file.write_text("rules: []")
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
            rule_file.write_text("rules: changed")
            self.assertEqual(reviewed_findings(root, config, [finding], before), [finding])
            rule_file.write_text("rules: []")
            (source / "guard.py").write_text("guard = False\n")
            self.assertEqual(reviewed_findings(root, config, [finding, other], before), [finding, other])
