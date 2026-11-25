"""Check that G-128 evidence remains complete and independently traceable."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "backend/docs/evidence/source-ledger.json"
CHECKER = ROOT / "backend/dev/bin/check-source-ledger"


class SourceLedgerTests(unittest.TestCase):
    def check(self, ledger):
        return subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(ledger)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_repository_ledger_covers_recorded_claims(self):
        result = self.check(LEDGER)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_missing_claim_and_invalid_evidence(self):
        cases = {
            "missing claim": lambda rows: rows.pop(0),
            "duplicate claim": lambda rows: rows.append(rows[0]),
            "changed claim": lambda rows: rows[0].update(claim="Unrelated claim"),
            "missing source": lambda rows: rows[0].update(source=""),
            "invalid date": lambda rows: rows[0].update(verified_on="2026-02-31"),
            "missing method": lambda rows: rows[0].update(method=" "),
            "unpinned evidence": lambda rows: rows[0].update(
                evidence="https://github.com/karacaismail/frappesetup/blob/backend/src/content/docs/izlenebilirlik.md",
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                rows = json.loads(LEDGER.read_text(encoding="utf-8"))
                mutate(rows)
                path = Path(directory) / "ledger.json"
                path.write_text(json.dumps(rows), encoding="utf-8")
                result = self.check(path)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("source ledger:", result.stderr)


if __name__ == "__main__":
    unittest.main()
