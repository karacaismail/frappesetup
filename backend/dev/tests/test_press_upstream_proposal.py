"""The Press upstream proposal is ready in the repository and has not been sent (decision O-57).

The proposal removes the need for the source parts of dev/press/patch-py314.sh. It is a Git mbox
patch series for Press v0.154.1 and an English pull request text. The project owner sends it.

These tests read files only. The clean "git apply --check" against Press v0.154.1 needs a Press
checkout; the command and its result are in docs/handoff/press-upstream-proposal.md.
"""

import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PROPOSAL = BACKEND / "docs" / "upstream" / "press-python314"
PATCH = PROPOSAL / "0001-python-313-frappe-16-imports.patch"
PULL_REQUEST = PROPOSAL / "pull-request.md"
HANDOFF = BACKEND / "docs" / "handoff" / "press-upstream-proposal.md"
RECORD = BACKEND / "PROJECT-RECORD.md"
NOTE = BACKEND / "docs" / "press-python314-upstream.md"

PRESS_COMMIT = "7a4384d5eec9f0f0dce4124e9dd48b106e51222f"
IDENTITY = "karacaismail <35493655+karacaismail@users.noreply.github.com>"
EXPECTED_FILES = {
    "press/press/doctype/deploy_candidate/cache_utils.py",
    "press/press/doctype/deploy_candidate/test_deploy_candidate.py",
    "press/saas/doctype/product_trial_request/product_trial_request.py",
    "press/api/cookies.py",
}
# Press commitlint: conventional type, kebab-case scope, sentence-case subject, at most 72 characters.
HEADER = re.compile(r"^(fix|feat|refactor|chore|test|docs)\([a-z0-9]+(-[a-z0-9]+)*\): [A-Z]\S.*$")


def subjects(text):
    """Commit headers of an mbox series; git wraps a long Subject onto indented lines."""
    found = re.findall(r"^Subject: \[PATCH \d+/\d+\] (.+(?:\n .+)*)", text, re.M)
    return [" ".join(part.strip() for part in subject.splitlines()) for subject in found]


class PatchSeries(unittest.TestCase):
    def setUp(self):
        self.text = PATCH.read_text()

    def test_patch_is_a_git_mbox_series_from_the_project_identity(self):
        authors = re.findall(r"^From: (.+)$", self.text, re.M)
        self.assertEqual(len(authors), 3)
        self.assertEqual(set(authors), {IDENTITY})
        self.assertEqual(len(re.findall(r"^From [0-9a-f]{40} ", self.text, re.M)), 3)

    def test_patch_carries_no_ai_signature_or_co_author(self):
        forbidden_words = ("Co-Authored-By", "Co-authored-by", "Generated with", "Claude", "anthropic")
        for forbidden in forbidden_words:
            self.assertNotIn(forbidden, self.text)

    def test_headers_follow_press_commitlint(self):
        headers = subjects(self.text)
        self.assertEqual(len(headers), 3)
        for header in headers:
            self.assertLessEqual(len(header), 72, header)
            self.assertRegex(header, HEADER)

    def test_patch_touches_only_the_three_source_blockers(self):
        # Dependency pins and Telegram stay out: they belong to separate upstream discussions.
        touched = set(re.findall(r"^diff --git a/(\S+) b/\1$", self.text, re.M))
        self.assertEqual(touched, EXPECTED_FILES)
        for out_of_scope in ("pyproject.toml", "telegram_utils.py"):
            self.assertNotIn(out_of_scope, self.text)

    def test_fixes_match_the_documented_blockers(self):
        self.assertIn("+class CommandOutput(TypedDict):", self.text)
        self.assertIn("-\tcwd=str,", self.text)
        self.assertIn("+\tclass AppInfo(TypedDict):", self.text)
        self.assertIn("-from frappe.utils.telemetry import init_telemetry", self.text)
        self.assertIn("+from press.utils.telemetry import init_telemetry", self.text)
        self.assertIn("-from frappe.oauth import get_cookie_dict_from_headers", self.text)
        self.assertIn('+\tcookie_perms = frappe.local.request.cookies.get("cookie_perms")', self.text)


class PullRequestText(unittest.TestCase):
    def setUp(self):
        self.text = PULL_REQUEST.read_text()

    def test_title_follows_press_commitlint(self):
        title = re.search(r"^Title: `(.+)`$", self.text, re.M)
        self.assertIsNotNone(title)
        self.assertLessEqual(len(title.group(1)), 72)
        self.assertRegex(title.group(1), HEADER)

    def test_text_is_english_and_names_the_errors(self):
        for word in ("ğ", "ş", "ı", "İ"):
            self.assertNotIn(word, self.text)
        for error in (
            "TypedDict() got an unexpected keyword argument 'cwd'",
            "cannot import name 'init_telemetry' from 'frappe.utils.telemetry'",
            "cannot import name 'get_cookie_dict_from_headers' from 'frappe.oauth'",
        ):
            self.assertIn(error, self.text)

    def test_paragraphs_are_not_hard_wrapped(self):
        # Press AGENTS.md: never hard-wrap the PR description.
        body = self.text.split("\n---\n", 1)[1]
        structured = ("-", "|", "#", "1.", "2.", "3.", ">")
        for block in body.split("```")[0::2]:
            for paragraph in block.split("\n\n"):
                lines = [line for line in paragraph.splitlines() if line.strip()]
                if lines and not any(line.lstrip().startswith(structured) for line in lines):
                    self.assertEqual(len(lines), 1, paragraph)

    def test_text_has_no_ai_signature(self):
        for forbidden in ("Generated with", "Claude", "Co-Authored-By"):
            self.assertNotIn(forbidden, self.text)


class NotSentYet(unittest.TestCase):
    def test_handoff_says_sending_waits_for_owner_approval(self):
        text = HANDOFF.read_text()
        self.assertIn("gönderilmedi", text)
        self.assertIn("proje sahibinin onayını bekler", text)
        self.assertIn("apply --check -v", text)
        self.assertIn(PRESS_COMMIT, text)

    def test_record_and_note_point_at_the_proposal(self):
        record = RECORD.read_text()
        self.assertIn("- **O-57. Press'e gidecek öneri depoda hazırdır ve gönderilmez.**", record)
        self.assertIn("docs/upstream/press-python314/", record)
        self.assertIn("upstream/press-python314/", NOTE.read_text())


if __name__ == "__main__":
    unittest.main()
