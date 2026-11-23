# SPDX-License-Identifier: MIT
"""Action decisions of the Frappe complement layer (G-161, G-166, G-167).

Keycloak answers who the person is. This module answers whether the person may take one action
now. It has no Frappe import: Frappe passes in the evidence it holds (membership, verification
results) and turns owner tasks into its own task records.

Each control of an action answers three questions:
1. Does the control apply to this action?
2. If it applies, is it required?
3. What does the current server evidence say?

A required control with an empty rule gives "configuration_required" and a task for the rule
owner. A required control without valid evidence gives "denied". A "ready" result names its
action and the policy version. The final step calls ``confirm``, which checks both again.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping

POLICY_FILE = Path(__file__).resolve().parents[1] / "policy" / "actions.json"
READY = "ready"
DENIED = "denied"
CONFIGURATION_REQUIRED = "configuration_required"
RULE_KEYS = {"id", "owner", "value", "description"}
ACTION_KEYS = {"id", "description", "controls"}
CONTROL_KEYS = {"id", "applies", "required", "evidence", "rules"}


class PolicyError(ValueError):
    """The policy file breaks a rule."""


@dataclass(frozen=True)
class Result:
    status: str
    action: str
    policy_version: str
    reasons: tuple = ()
    owner_tasks: tuple = field(default=())


def _require_keys(item: object, allowed: set, where: str) -> dict:
    if not isinstance(item, dict):
        raise PolicyError(f"{where} must be an object.")
    if set(item) != allowed:
        raise PolicyError(f"{where} must have exactly these keys: {', '.join(sorted(allowed))}.")
    if not isinstance(item["id"], str) or not item["id"]:
        raise PolicyError(f"{where} needs an id.")
    return item


def _evidence_is_valid(item: object, now: datetime) -> bool:
    if not isinstance(item, Mapping) or item.get("status") != "valid":
        return False
    expires = item.get("expiresAt")
    if expires is None:
        return True
    try:
        return datetime.fromisoformat(str(expires)) > now
    except ValueError:
        return False


class Policy:
    def __init__(self, data: dict):
        if not isinstance(data, dict) or set(data) != {"rules", "actions"}:
            raise PolicyError("The policy needs exactly 'rules' and 'actions'.")
        self.rules = {}
        for rule in data["rules"]:
            rule = _require_keys(rule, RULE_KEYS, "A rule")
            if not isinstance(rule["owner"], str) or not rule["owner"].strip():
                raise PolicyError(f"Rule {rule['id']} needs an owner.")
            if rule["id"] in self.rules:
                raise PolicyError(f"Rule {rule['id']} is listed twice.")
            self.rules[rule["id"]] = rule
        self.actions = {}
        for action in data["actions"]:
            action = _require_keys(action, ACTION_KEYS, "An action")
            if action["id"] in self.actions:
                raise PolicyError(f"Action {action['id']} is listed twice.")
            for control in action["controls"]:
                control = _require_keys(control, CONTROL_KEYS, f"A control of {action['id']}")
                if not isinstance(control["applies"], bool) or not isinstance(control["required"], bool):
                    raise PolicyError(f"Control {control['id']}: applies and required must be true or false.")
                if not isinstance(control["evidence"], str) or not control["evidence"]:
                    raise PolicyError(f"Control {control['id']} needs an evidence name.")
                unknown = [r for r in control["rules"] if r not in self.rules]
                if unknown:
                    raise PolicyError(f"Control {control['id']} names unknown rules: {', '.join(unknown)}.")
            self.actions[action["id"]] = action
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.version = hashlib.sha256(canonical).hexdigest()

    def evaluate(self, action_id: str, evidence: Mapping[str, object], now: datetime) -> Result:
        """Judge one action. ``evidence`` is what the server holds now, never token claims."""
        action = self.actions.get(action_id)
        if action is None:
            return Result(DENIED, action_id, self.version, ("unknown-action",))
        reasons, tasks = [], []
        for control in action["controls"]:
            if not control["applies"]:
                continue
            empty = [r for r in control["rules"] if self.rules[r]["value"] is None]
            if not control["required"]:
                continue
            if empty:
                tasks.extend(
                    {"rule": r, "owner": self.rules[r]["owner"], "action": action_id} for r in empty
                )
                continue
            if not _evidence_is_valid(evidence.get(control["evidence"]), now):
                reasons.append(control["id"])
        if tasks:
            return Result(CONFIGURATION_REQUIRED, action_id, self.version, ("configuration-required",), tuple(tasks))
        if reasons:
            return Result(DENIED, action_id, self.version, tuple(reasons))
        return Result(READY, action_id, self.version)

    def confirm(self, earlier: Result, action_id: str, evidence: Mapping[str, object], now: datetime) -> Result:
        """Final step: the earlier result must be for this action and this policy, and still hold."""
        if earlier.status != READY or earlier.action != action_id:
            return Result(DENIED, action_id, self.version, ("result-not-for-this-action",))
        if earlier.policy_version != self.version:
            return Result(DENIED, action_id, self.version, ("policy-changed",))
        return self.evaluate(action_id, evidence, now)


def load_policy(path: Path = POLICY_FILE) -> Policy:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as error:
        raise PolicyError(f"The policy file is not valid JSON ({error.__class__.__name__}).") from None
    return Policy(data)
