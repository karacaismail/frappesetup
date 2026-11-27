"""The Jenkins handoff note names the environment approver by role, never by person.

Decision of 26 November 2026: one person approves every change on a remote server. The repository
does not hold that person's name. The note backend/docs/handoff/jenkins-credentials.md calls the
person "ortam onaylayıcısı", asks for that approval before steps that reach a remote server, does
not use the older wording "ortamın sorumlusundan" and does not list the server fee as an open item:
the fee is approved.

Person names are checked with the release residue scanner (backend/dev/tests/test_release_residue.py),
so the list of names stays in one place and only as digests.
"""

import importlib.util
import re
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
BACKEND = DEPLOY.parent
NOTE = BACKEND / "docs" / "handoff" / "jenkins-credentials.md"
RESIDUE = BACKEND / "dev" / "tests" / "test_release_residue.py"

APPROVER = "ortam onaylayıcısı"
OLD_WORDING = "ortamın sorumlusundan"
# A line that names the fee and calls it undecided, waiting or open.
OPEN_FEE = re.compile(
    r"(?i)ücret\w*\b.*\b(?:açık|bekl\w*|onaylanmadı|netleş\w*|karar\w*)"
    r"|(?i:açık|bekl\w*|karar\w*)\b.*\bücret"
)
# Steps that reach the rc or prod server must ask the approver first.
REMOTE_STEP = re.compile(r"`(?:rc|prod)`|\b(?:rc|prod)\b ortam")
APPROVAL = "ortam onaylayıcısından onay alın"


def residue_scanner():
    spec = importlib.util.spec_from_file_location("release_residue", RESIDUE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scan_text


def open_fee_lines(text):
    """Return the lines that list the server fee as an open item."""
    return [line.strip() for line in text.splitlines() if OPEN_FEE.search(line)]


def person_name_lines(text):
    return [line for kind, line in residue_scanner()(NOTE.name, text) if kind == "person-name"]


class EnvironmentApprover(unittest.TestCase):
    def setUp(self):
        self.text = NOTE.read_text()

    def test_note_names_the_environment_approver(self):
        self.assertIn(APPROVER, self.text)

    def test_note_does_not_use_the_old_wording(self):
        self.assertNotIn(OLD_WORDING, self.text)

    def test_note_holds_no_person_name(self):
        self.assertEqual(person_name_lines(self.text), [])

    def test_note_does_not_list_the_fee_as_open(self):
        self.assertEqual(open_fee_lines(self.text), [])

    def test_every_rc_and_prod_step_asks_the_approver(self):
        steps = [line for line in self.text.splitlines()
                 if re.match(r"\d+\. ", line) and REMOTE_STEP.search(line)]
        self.assertTrue(steps, "the note has no numbered step for rc or prod")
        for step in steps:
            self.assertIn(APPROVAL, step)


class ChecksFire(unittest.TestCase):
    """Synthetic samples prove each check finds what it looks for."""

    def test_open_fee_check(self):
        self.assertEqual(len(open_fee_lines("Sunucu ücreti henüz açık konu.")), 1)
        self.assertEqual(len(open_fee_lines("Ücret kararı bekleniyor.")), 1)
        self.assertEqual(open_fee_lines("Bir anahtar yalnız kendi ortamını açar."), [])

    def test_remote_step_check(self):
        self.assertTrue(REMOTE_STEP.search("3. `prod` ortamına geçin."))
        self.assertIsNone(REMOTE_STEP.search("3. Ajanı hazırlayın."))


if __name__ == "__main__":
    unittest.main()
