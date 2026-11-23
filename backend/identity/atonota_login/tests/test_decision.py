"""Action decision tests (G-161, G-166, G-167).

Expected rules, from the requirements:
- G-161: every action is judged on its own. Each control answers three questions: does it
  apply, is it required, what does the current evidence say. An unknown required condition
  never gives "ready". "Ready" holds for one action only. The final step checks again. The
  decision does not use the role in the token.
- G-167: a rule without a value keeps the action closed with "configuration required" and
  gives its owner a task. Example values are not product decisions.
- G-166: no paid plan opens before the price decision closes.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atonota_login import decision
from atonota_login.decision import PolicyError

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
VALID = {"status": "valid"}


def evidence(**items):
    return {key.replace("_", "-"): value for key, value in items.items()}


class ShippedPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = decision.load_policy()

    def test_every_rule_has_an_owner_and_no_value_yet(self):
        # G-167: the values are product decisions that are still open. The file holds none.
        self.assertTrue(self.policy.rules)
        for rule in self.policy.rules.values():
            self.assertTrue(rule["owner"], rule["id"])
            self.assertIsNone(rule["value"], rule["id"])

    def test_g167_named_rules_are_listed(self):
        names = {
            "verification-provider", "country-document-rule", "proof-lifetimes",
            "retry-limits", "verification-data-region", "guest-actions",
        }
        self.assertLessEqual(names, set(self.policy.rules))

    def test_member_without_membership_cannot_order(self):
        # G-161 acceptance: identity confirmed, no membership.
        result = self.policy.evaluate("place-order", evidence(identity=VALID), NOW)
        self.assertEqual(result.status, "denied")
        self.assertIn("membership", result.reasons)

    def test_token_role_does_not_replace_membership(self):
        # The caller passes only server evidence. A role claim is not evidence.
        claims = evidence(identity=VALID, token_roles={"status": "valid", "roles": ["member"]})
        self.assertEqual(self.policy.evaluate("place-order", claims, NOW).status, "denied")

    def test_member_can_order(self):
        result = self.policy.evaluate("place-order", evidence(identity=VALID, membership=VALID), NOW)
        self.assertEqual(result.status, "ready")

    def test_expired_evidence_is_not_valid(self):
        old = {"status": "valid", "expiresAt": (NOW - timedelta(seconds=1)).isoformat()}
        result = self.policy.evaluate("place-order", evidence(identity=VALID, membership=old), NOW)
        self.assertEqual(result.status, "denied")

    def test_actions_differ(self):
        # A form needs less than an order.
        self.assertEqual(self.policy.evaluate("submit-form", evidence(identity=VALID), NOW).status, "ready")

    def test_empty_rule_keeps_identity_check_closed_and_creates_owner_tasks(self):
        result = self.policy.evaluate("identity-verification", evidence(identity=VALID), NOW)
        self.assertEqual(result.status, "configuration_required")
        owners = {task["rule"]: task["owner"] for task in result.owner_tasks}
        self.assertIn("verification-provider", owners)
        for task in result.owner_tasks:
            self.assertEqual(task["action"], "identity-verification")
            self.assertEqual(task["owner"], self.policy.rules[task["rule"]]["owner"])

    def test_paid_plan_cannot_open_before_the_price_decision(self):
        result = self.policy.evaluate("open-paid-plan", evidence(identity=VALID, membership=VALID), NOW)
        self.assertEqual(result.status, "configuration_required")
        self.assertEqual([t["rule"] for t in result.owner_tasks], ["paid-plan-pricing"])

    def test_guest_actions_stay_closed(self):
        self.assertEqual(self.policy.evaluate("guest-action", {}, NOW).status, "configuration_required")

    def test_unknown_action_is_denied(self):
        self.assertEqual(self.policy.evaluate("no-such-action", evidence(identity=VALID), NOW).status, "denied")


class FinalCheckTest(unittest.TestCase):
    def setUp(self):
        self.policy = decision.load_policy()
        self.proof = evidence(identity=VALID, membership=VALID)

    def test_final_step_accepts_an_unchanged_result(self):
        ready = self.policy.evaluate("place-order", self.proof, NOW)
        self.assertEqual(self.policy.confirm(ready, "place-order", self.proof, NOW).status, "ready")

    def test_ready_result_holds_for_its_action_only(self):
        ready = self.policy.evaluate("submit-form", self.proof, NOW)
        self.assertEqual(self.policy.confirm(ready, "place-order", self.proof, NOW).status, "denied")

    def test_rule_change_during_the_action_voids_the_result(self):
        ready = self.policy.evaluate("place-order", self.proof, NOW)
        data = json.loads(decision.POLICY_FILE.read_text(encoding="utf-8"))
        data["actions"] = [a for a in data["actions"] if a["id"] != "submit-form"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "policy.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            changed = decision.load_policy(path)
        result = changed.confirm(ready, "place-order", self.proof, NOW)
        self.assertEqual(result.status, "denied")
        self.assertIn("policy-changed", result.reasons)

    def test_final_step_checks_the_evidence_again(self):
        ready = self.policy.evaluate("place-order", self.proof, NOW)
        revoked = evidence(identity=VALID, membership={"status": "revoked"})
        self.assertEqual(self.policy.confirm(ready, "place-order", revoked, NOW).status, "denied")


class PolicyFileTest(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "policy.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return decision.load_policy(path)

    def base(self):
        return {
            "rules": [{"id": "a-rule", "owner": "product-owner", "value": None, "description": "x"}],
            "actions": [{"id": "act", "description": "x", "controls": [
                {"id": "identity", "applies": True, "required": True, "evidence": "identity", "rules": []},
            ]}],
        }

    def test_bad_files_are_refused(self):
        changes = {
            "rule without owner": lambda d: d["rules"][0].update(owner=""),
            "unknown rule": lambda d: d["actions"][0]["controls"][0].update(rules=["missing"]),
            "applies is not a boolean": lambda d: d["actions"][0]["controls"][0].update(applies="maybe"),
            "duplicate action": lambda d: d["actions"].append(dict(d["actions"][0])),
            "unknown key": lambda d: d["actions"][0]["controls"][0].update(tokenRole="member"),
        }
        for label, change in changes.items():
            with self.subTest(label):
                data = self.base()
                change(data)
                with self.assertRaises(PolicyError):
                    self.load(data)

    def test_control_that_does_not_apply_is_skipped(self):
        data = self.base()
        data["actions"][0]["controls"][0]["applies"] = False
        self.assertEqual(self.load(data).evaluate("act", {}, NOW).status, "ready")

    def test_optional_control_with_an_empty_rule_does_not_block(self):
        data = self.base()
        data["actions"][0]["controls"].append(
            {"id": "extra", "applies": True, "required": False, "evidence": "extra", "rules": ["a-rule"]})
        self.assertEqual(self.load(data).evaluate("act", {"identity": VALID}, NOW).status, "ready")


if __name__ == "__main__":
    unittest.main()
