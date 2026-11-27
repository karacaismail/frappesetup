"""Backend guidance must describe the PR and ProPR merge flow (AJA-1508)."""

import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GUIDES = ("AGENTS.md", "CLAUDE.md")
DOCS = GUIDES + ("PROJECT-RECORD.md",)

# Sentences that said the backend branch stays local.
STALE = (
    re.compile(r"Push yapmayın\. Pull request açmayın"),
    re.compile(r"Push, pull request ve canlıya yükleme bu turda yapılmaz"),
    re.compile(r"Dalları orkestratör birleştirir"),
    re.compile(r"Orkestratör dalınızı inceler ve birleştirir"),
    re.compile(r"backend[^.\n]*GitHub'a gitmez"),
)


class BranchFlowDocsTests(unittest.TestCase):
    def test_no_document_says_backend_stays_local(self):
        for name in DOCS:
            text = (BACKEND / name).read_text(encoding="utf-8")
            for pattern in STALE:
                with self.subTest(doc=name, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))

    def test_documents_name_the_pr_and_propr_rule(self):
        for name in DOCS:
            text = (BACKEND / name).read_text(encoding="utf-8")
            with self.subTest(doc=name):
                self.assertIn("`backend` dalına PR ile girilir", text)
                self.assertIn("PR'ı ProPR birleştirir", text)

    def test_guides_forbid_local_merge_and_direct_push(self):
        for name in GUIDES:
            text = (BACKEND / name).read_text(encoding="utf-8")
            with self.subTest(doc=name):
                self.assertIn("`backend` dalına yerelde birleştirme yapmayın", text)
                self.assertIn("`backend` dalına doğrudan push etmeyin", text)

    def test_guides_stay_identical(self):
        self.assertEqual(
            (BACKEND / "AGENTS.md").read_text(encoding="utf-8"),
            (BACKEND / "CLAUDE.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
