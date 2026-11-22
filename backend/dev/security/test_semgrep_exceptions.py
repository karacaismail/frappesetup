import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from semgrep_exceptions import RULES, reviewed_findings, source_digest


class SemgrepExceptionsTests(unittest.TestCase):
    def git(self, root, *arguments):
        subprocess.run([shutil.which("git"), "-C", str(root), *arguments], check=True)

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
