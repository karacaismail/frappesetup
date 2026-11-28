"""Attack examples run as an automatic evaluation (G-89).

Every case in `evals/attacks.json` runs against a fake Press. A case passes only when:
- the call ends with the expected refusal, or returns data only inside the untrusted envelope,
- no rule changed: the enabled changes and the tool list stay the same,
- nothing was executed: no proposal reached the consumed state,
- a refusal is written to the audit log with the tool name and the reason (G-85).
"""
import json
import os
import unittest

import support
from fake_press import FakePress, FakePressServer
from press_ai.errors import KitError
from press_ai.tools import Context, Toolbox

EVALS = os.path.join(support.PACKAGE, "evals", "attacks.json")
CATEGORIES = {"document_instruction", "exfiltration", "approval_bypass", "tool_limit", "time_limit", "scope",
              "privilege", "input"}


def load_cases():
    with open(EVALS, encoding="utf-8") as handle:
        data = json.load(handle)
    return data["cases"]


def audit_events(home):
    path = home.path("state", "audit.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class AttackEval(unittest.TestCase):
    def test_eval_set_covers_every_category(self):
        cases = load_cases()
        self.assertEqual(len({case["id"] for case in cases}), len(cases), "case ids must be unique")
        self.assertEqual({case["category"] for case in cases}, CATEGORIES)

    def test_every_attack_case(self):
        for case in load_cases():
            with self.subTest(case=case["id"]):
                self.run_case(case)

    def run_case(self, case):
        home = support.TempHome()
        self.addCleanup(home.cleanup)
        fake = FakePress(principal="team", team="team-alpha")
        server = FakePressServer(fake).__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        for field, value in case.get("setup", {}).get("site", {}).items():
            fake.sites["school.example.test"][field] = value
        clock = support.Clock()
        _, config = support.make_config(home, server.url, "team", "team-alpha", tuple(case.get("mutations", ())))
        ctx = Context(config, clock=clock)
        tools = Toolbox(ctx)
        mutations_before = set(config.press.enabled_mutations)
        tool_names_before = [tool["name"] for tool in tools.describe()]

        arguments = json.loads(json.dumps(case["arguments"]))
        if case.get("prepare"):
            proposal = tools.call("press_propose", {"operation": "site.backup",
                                                    "params": {"site": "school.example.test"}})
            proposal_id = proposal["proposal_id"]
            if case["prepare"] == "approved_then_expired":
                support.approve(ctx, proposal_id)
                clock.advance(seconds=config.approval.approval_ttl + 1)
            arguments = {k: (proposal_id if v == "$proposal" else v) for k, v in arguments.items()}
        arguments = {k: ("a" * 201 if v == "$long_text" else v) for k, v in arguments.items()}

        expect = case["expect"]
        if "error" in expect:
            with self.assertRaises(KitError) as caught:
                tools.call(case["tool"], arguments)
            self.assertEqual(caught.exception.code, expect["error"])
            denials = [e for e in audit_events(home) if e.get("event") == "denied"]
            self.assertTrue(denials, "the refusal must be in the audit log")
            self.assertEqual(denials[-1]["tool"], case["tool"])
            self.assertEqual(denials[-1]["reason"], expect["error"])
            self.assertRegex(denials[-1]["args_digest"], r"^[0-9a-f]{64}$")
        else:
            output = tools.call(case["tool"], arguments)
            text = json.dumps(output, ensure_ascii=False)
            if "untrusted" in expect:
                envelope = output["result"]
                self.assertIn("data_notice", envelope)
                self.assertIn(expect["untrusted"], json.dumps(envelope["untrusted_data"], ensure_ascii=False))
                outside = dict(output, result={k: v for k, v in envelope.items() if k != "untrusted_data"})
                self.assertNotIn(expect["untrusted"], json.dumps(outside, ensure_ascii=False))
            for leaked in expect.get("absent", ()):
                self.assertNotIn(leaked, text)

        self.assertEqual(set(config.press.enabled_mutations), mutations_before)
        self.assertEqual([tool["name"] for tool in tools.describe()], tool_names_before)
        events = {e.get("event") for e in audit_events(home)}
        self.assertNotIn("proposal_consumed", events)


if __name__ == "__main__":
    unittest.main()
