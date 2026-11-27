"""Apply the QA-owned scanner to the site scope without weakening its global gate."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "brand_scanner", ROOT / "backend/deploy/tests/test_brand_hardcode.py"
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class SiteBrandTests(unittest.TestCase):
    def test_product_placeholder_has_no_name_dependent_suffix(self):
        root, files = scanner.tracked_files()
        hits = []
        for path in files:
            if not path.startswith("src/") or Path(path).suffix not in (".md", ".json"):
                continue
            for number, line in enumerate((root / path).read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\{\{PRODUCT_NAME\}\}['’ʼ]", line):
                    hits.append(f"{path}:{number}")
        self.assertEqual(hits, [], "Use a name-independent phrase such as 'ürününü': " + ", ".join(hits))

    def test_site_has_no_hardcoded_brand(self):
        root, files = scanner.tracked_files()
        files = [path for path in files if path.startswith(("src/", "scripts/", "tests/"))]
        hits = scanner.find_hits(root, files, scanner.read_brand(scanner.BRAND_ENV),
                                 scanner.read_exclusions(scanner.EXCLUSIONS))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
