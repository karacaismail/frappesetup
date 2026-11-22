"""Check that the disposable Press setup installs its direct test dependencies."""

import re
import unittest
from pathlib import Path

PRESS_DEV = Path(__file__).resolve().parent
REPO = PRESS_DEV.parents[2]


class PressDependencyTest(unittest.TestCase):
    def test_test_environment_installs_declared_direct_dependencies(self):
        metadata = (REPO / "backend/apps/press_tr/pyproject.toml").read_text()
        optional = re.search(r"(?ms)^\[project\.optional-dependencies\]\s*\n(.*?)(?=^\[|\Z)", metadata)
        self.assertIsNotNone(optional)
        requirements = re.search(r"(?ms)^test\s*=\s*\[(.*?)\]", optional.group(1))
        self.assertIsNotNone(requirements)
        for dependency in ("cryptography", "Jinja2", "PyJWT", "PyYAML"):
            with self.subTest(dependency=dependency):
                self.assertRegex(requirements.group(1), rf'(?i)"{dependency}(?=[<>=~"])')

        installer = (PRESS_DEV / "install.sh").read_text()
        self.assertIn("apps/press_tr[test]", installer)

    def test_development_guide_records_the_test_extra(self):
        guide = (PRESS_DEV / "README.md").read_text()
        self.assertIn("apps/press_tr[test]", guide)
