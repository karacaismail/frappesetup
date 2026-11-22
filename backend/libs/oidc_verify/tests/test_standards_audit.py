"""Standards self audit (docs/standartlar/frappe-python-standartlari.md) for this library.

A-1 and A-2: before writing new code, compare with the ready solution and write down the remaining gap.
PyJWT, which this library already depends on, ships `jwt.PyJWKClient`.
R-2: a `noqa` comment names the rule and gives its reason.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOQA = re.compile(r"#\s*noqa(?::\s*([A-Z0-9, ]+))?(.*)$")


class ReuseDecisionTest(unittest.TestCase):
    def test_readme_compares_with_pyjwkclient_and_names_the_gap(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("PyJWKClient", readme)
        section = readme.split("PyJWKClient", 1)[1][:2000]
        for gap in ("max_stale_seconds", "total_timeout", "wait_timeout", "max_bytes", "yönlendirme"):
            self.assertIn(gap, section, gap)


class NoqaReasonTest(unittest.TestCase):
    def test_every_noqa_names_a_rule_and_a_reason(self):
        problems = []
        for path in sorted([*ROOT.joinpath("src").rglob("*.py"), *ROOT.joinpath("tests").rglob("*.py")]):
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, start=1):
                match = NOQA.search(line)
                if match is None or "NOQA = re.compile" in line:
                    continue
                codes, rest = match.group(1), match.group(2).strip()
                previous = lines[number - 2].strip() if number > 1 else ""
                has_reason = rest.startswith("-") and len(rest) > 2 or previous.startswith("#")
                if not codes or not has_reason:
                    problems.append(f"{path.name}:{number}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
