"""Exercise the config audit through its command-line entry point."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / "config_layers.py"


class ConfigLayersTest(unittest.TestCase):
    def audit(self, common, sites):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "common_site_config.json").write_text(json.dumps(common))
            for site, config in sites.items():
                (root / site).mkdir()
                (root / site / "site_config.json").write_text(json.dumps(config))
            return subprocess.run(
                [sys.executable, "-B", str(AUDIT), str(root)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_accepts_correct_layers_and_leaves_unlisted_keys_alone(self):
        result = self.audit(
            {"mail_port": 2525, "pause_scheduler": True},
            {"a.localhost": {"db_name": "a", "sk_example": "fixture", "pause_scheduler": True}},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reports_all_misplaced_keys_without_values(self):
        result = self.audit(
            {"encryption_key": "fixture-secret", "sk_example": "example-secret"},
            {"b.localhost": {"mail_port": 2525, "mail_extra": "mail-secret"}},
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("common_site_config.json: encryption_key", result.stderr)
        self.assertIn("common_site_config.json: sk_example", result.stderr)
        self.assertIn("b.localhost/site_config.json: mail_port", result.stderr)
        self.assertIn("b.localhost/site_config.json: mail_extra", result.stderr)
        self.assertNotIn("secret", result.stderr)
        self.assertNotIn("2525", result.stderr)

    def test_rejects_cors_in_both_layers(self):
        result = self.audit({"allow_cors": "*"}, {"a.localhost": {"allow_cors": "*"}})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.count("allow_cors"), 2)

    def test_rejects_invalid_config_without_echoing_it(self):
        result = self.audit({"mail_port": 2525}, {"a.localhost": ["fixture-secret"]})
        self.assertEqual(result.returncode, 1)
        self.assertIn("a.localhost/site_config.json", result.stderr)
        self.assertNotIn("fixture-secret", result.stderr)
