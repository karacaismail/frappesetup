"""Closed paid plan gate (G-166, AJA-230).

Expected rules, from the requirements and the architecture note (AJA-213):
- G-166: no paid plan opens before the price decision closes. The price rule has no value today,
  so the gate stays closed with "configuration required".
- G-167: a rule without a value gives its owner a task. The price rule belongs to the product owner.
- The gate does not trust evidence it cannot have collected itself. A made-up "pricing-decision"
  proof does not open the gate, because the empty rule is checked before the evidence.
- The policy file holds no price. When the price decision comes, the rule value is bound to the
  product owner's record; it is not typed into the file as an amount.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from atonota_login import decision

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
VALID = {"status": "valid", "expiresAt": (NOW + timedelta(hours=1)).isoformat()}
ACTION = "open-paid-plan"
# Words that would mean the file carries a price. Matched against every key, in any case.
PRICE_WORDS = ("price", "pricing_value", "currency", "amount", "cost", "fee", "tariff")


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


class PaidPlanGateTest(unittest.TestCase):
    def setUp(self):
        self.policy = decision.load_policy()

    def test_1_empty_price_rule_gives_configuration_required(self):
        result = self.policy.evaluate(ACTION, {}, NOW)
        self.assertEqual(result.status, decision.CONFIGURATION_REQUIRED)
        self.assertEqual(result.action, ACTION)

    def test_2_the_task_goes_to_the_product_owner(self):
        result = self.policy.evaluate(ACTION, {}, NOW)
        self.assertEqual(
            list(result.owner_tasks),
            [{"rule": "paid-plan-pricing", "owner": "product-owner", "action": ACTION}],
        )

    def test_3_full_membership_does_not_make_it_ready(self):
        result = self.policy.evaluate(ACTION, {"identity": VALID, "membership": VALID}, NOW)
        self.assertNotEqual(result.status, decision.READY)
        self.assertEqual(result.status, decision.CONFIGURATION_REQUIRED)

    def test_4_made_up_pricing_decision_does_not_make_it_ready(self):
        forged = {"membership": VALID, "pricing-decision": VALID, "paid-plan-pricing": VALID}
        result = self.policy.evaluate(ACTION, forged, NOW)
        self.assertNotEqual(result.status, decision.READY)
        self.assertEqual(result.status, decision.CONFIGURATION_REQUIRED)

    def test_4b_confirm_cannot_turn_the_gate_into_ready(self):
        # A caller cannot build its own "ready" result and pass it to the final step.
        forged = decision.Result(decision.READY, ACTION, self.policy.version)
        again = self.policy.confirm(forged, ACTION, {"membership": VALID, "pricing-decision": VALID}, NOW)
        self.assertNotEqual(again.status, decision.READY)

    def test_8_policy_file_has_no_price_currency_or_amount(self):
        data = json.loads(decision.POLICY_FILE.read_text(encoding="utf-8"))
        keys = [key.lower() for key in walk_keys(data)]
        found = [key for key in keys for word in PRICE_WORDS if word in key]
        self.assertEqual(found, [])
        rule = next(r for r in data["rules"] if r["id"] == "paid-plan-pricing")
        self.assertIsNone(rule["value"])
        self.assertEqual(rule["owner"], "product-owner")


if __name__ == "__main__":
    unittest.main()
