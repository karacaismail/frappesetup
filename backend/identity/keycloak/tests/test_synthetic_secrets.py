"""Security scan findings (Gitleaks, generic-api-key) in this job's test files.

The values are made up for tests: the sample TOTP user lives only in the development realm, and the
event listener tests sign with a fixed test key. They are kept, and each line carries Gitleaks'
inline allow marker with the reason, so the source scan stays clean without a broad exception.
"""

from __future__ import annotations

import re
import unittest

from yardimci import KLASOR

# An assignment of a string literal to a SECRET or PASSWORD constant, in Python or in Java.
SECRET_LINE = re.compile(r"^\s*(?:private static final String\s+)?[A-Z_]*(?:SECRET|PASSWORD)[A-Z_]*\s*=\s*b?\"")
TEST_FILES = [
    KLASOR / "tests" / "test_second_factor.py",
    KLASOR / "tests" / "test_dev_script_secrets.py",
    *sorted((KLASOR / "event-listener" / "src" / "test").rglob("*.java")),
]


class SyntheticSecretTest(unittest.TestCase):
    def test_every_literal_test_secret_is_marked_as_synthetic(self):
        found = 0
        for path in TEST_FILES:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if SECRET_LINE.search(line):
                    found += 1
                    self.assertIn("gitleaks:allow", line, f"{path.name}:{number}")
                    self.assertIn("synthetic test value", line, f"{path.name}:{number}")
        self.assertGreaterEqual(found, 5)

    def test_sample_totp_secret_belongs_to_the_development_users_only(self):
        realm = (KLASOR / "realm" / "platform-realm.json").read_text(encoding="utf-8")
        users = (KLASOR / "realm" / "dev-users" / "platform-users-0.json").read_text(encoding="utf-8")
        self.assertNotIn("dev-totp-secret", realm)
        self.assertIn("dev-totp-secret-0123456789", users)


if __name__ == "__main__":
    unittest.main()
