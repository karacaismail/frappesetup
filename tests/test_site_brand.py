"""Apply the QA-owned scanner to the site scope without weakening its global gate."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "brand_scanner", ROOT / "backend/deploy/tests/test_brand_hardcode.py"
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class SiteBrandTests(unittest.TestCase):
    def test_site_has_no_hardcoded_brand(self):
        root, files = scanner.tracked_files()
        files = [path for path in files if path.startswith(("src/", "scripts/", "tests/"))]
        hits = scanner.find_hits(root, files, scanner.read_brand(scanner.BRAND_ENV),
                                 scanner.read_exclusions(scanner.EXCLUSIONS))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
