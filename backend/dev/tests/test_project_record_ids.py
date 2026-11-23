"""PROJECT-RECORD.md defines every decision id once.

Two branches once gave the same id O-43 to two decisions. A reference such as "(O-43)" could then
point at either decision.
"""

import collections
import re
import unittest
from pathlib import Path

RECORD = Path(__file__).resolve().parents[2] / "PROJECT-RECORD.md"
DECISION = re.compile(r"^- \*\*(O-\d+)\.", re.M)


class ProjectRecordIds(unittest.TestCase):
    def test_every_o_id_is_defined_once(self):
        ids = DECISION.findall(RECORD.read_text())
        self.assertTrue(ids)
        duplicates = sorted(name for name, count in collections.Counter(ids).items() if count > 1)
        self.assertEqual(duplicates, [])

    def test_semgrep_approval_decision_has_its_own_id(self):
        # The Press Semgrep decision entered the record second, so it moved to the first free id.
        text = RECORD.read_text()
        self.assertIn("- **O-43. Anonim yapma adımında 404 sonuç sayılmaz.**", text)
        self.assertIn("- **O-53. Press Semgrep onayları dosya listesine bağlıdır.**", text)


if __name__ == "__main__":
    unittest.main()
