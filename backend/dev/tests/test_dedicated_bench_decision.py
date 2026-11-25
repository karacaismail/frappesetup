"""G-40: the dedicated bench rule lives in one decision file only."""

import json
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
DECISION = BACKEND / "docs" / "decisions" / "0020-dedicated-bench.md"
RULE_KEY = "dedicated_bench_when_any"


def read_rule() -> dict:
    blocks = re.findall(r"```json\n(.*?)```", DECISION.read_text(encoding="utf-8"), re.S)
    rules = [json.loads(block) for block in blocks if RULE_KEY in block]
    if len(rules) != 1:
        raise AssertionError(f"{DECISION.name} needs exactly one {RULE_KEY} block")
    return rules[0]


class DedicatedBenchDecisionTests(unittest.TestCase):
    def test_rule_has_the_two_product_conditions(self):
        self.assertEqual(
            read_rule(),
            {RULE_KEY: [{"plan": "Kurumsal"}, {"has_custom_app": True}]},
        )

    def test_rule_is_not_copied_into_another_file(self):
        copies = [
            path.relative_to(BACKEND).as_posix()
            for path in BACKEND.rglob("*")
            if path.is_file()
            and path.suffix in {".md", ".py", ".json", ".yaml", ".yml", ".toml"}
            and path not in {DECISION, Path(__file__).resolve()}
            and RULE_KEY in path.read_text(encoding="utf-8", errors="ignore")
        ]
        self.assertEqual(copies, [])

    def test_handoff_note_points_to_the_decision(self):
        note = (BACKEND / "docs" / "handoff" / "g40-g41-platform-defaults.md").read_text(encoding="utf-8")
        self.assertIn("decisions/0020-dedicated-bench.md", note)
        self.assertNotIn("C durumundadır", note)


if __name__ == "__main__":
    unittest.main()
