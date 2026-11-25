"""Frappe link of the AtonotA Login action decision (G-161, G-166, G-167).

The rules live in the `atonota_login` package (`atonota_login.decision`). That package has no Frappe
code. This module is the thin Frappe layer around it:

1. It collects the evidence the server holds now, from Frappe records.
2. It turns "configuration_required" into one Frappe task per empty rule.
3. It runs the write of a final step only after `Policy.confirm` says "ready" again.

The caller never supplies evidence. Request fields and token roles are not read.
Membership is read from the server's `User.user_type` for now. Frappe derives that field from the
user's desk roles on save, so a desk role on the server record gives membership evidence. This is a
known debt until the organisation membership record exists (G-160, PROJECT-RECORD.md).
Contract: `backend/contracts/platform_core-identity.openapi.yaml`, tag `atonota-login`.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import frappe
from atonota_login import decision
from frappe import _

from platform_core.identity.exceptions import InvalidInput

MAX_ACTION_LENGTH = 140
# Evidence collected in one request holds for that moment only. It is not a proof lifetime
# (the "proof-lifetimes" rule has no value yet). The final step collects the evidence again.
SNAPSHOT = timedelta(microseconds=1)
TASK_ROLE = "System Manager"
TASK_MARK = "[AtonotA Login rule]"


class ActionRefused(frappe.PermissionError):
	"""The decision for the action is not "ready". The message names the decision state."""

	http_status_code = 403


class PendingWrites(frappe.ValidationError):
	"""The request already holds writes. A final step does not start then (AJA-264)."""

	http_status_code = 409


def now_utc() -> datetime:
	return datetime.now(UTC)


def _load_policy() -> decision.Policy:
	# Read for every check. The final step compares the policy versions of its two checks.
	return decision.load_policy()


def _proof(now: datetime) -> dict:
	return {"status": "valid", "expiresAt": (now + SNAPSHOT).isoformat()}


def collect_evidence(user: str, now: datetime) -> dict:
	"""Evidence for `user` from Frappe records. Token and request roles are not read.

	Membership comes from `user_type`, which Frappe derives from the server record's desk roles
	(known debt, G-160).
	"""
	if not user or user == "Guest":
		return {}
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not row or not row.enabled:
		return {}
	evidence = {}
	if frappe.db.exists("PLT Identity Link", {"user": user}):
		evidence["identity"] = _proof(now)
	if row.user_type == "System User":
		evidence["membership"] = _proof(now)
	return evidence


def _signed_in_user() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Sign in to continue.", context="platform_core.identity"), frappe.PermissionError)
	return user


def _as_dict(result: decision.Result) -> dict:
	return {
		"status": result.status,
		"action": result.action,
		"policy_version": result.policy_version,
		"reasons": list(result.reasons),
		"owner_tasks": [dict(task) for task in result.owner_tasks],
	}


def _task_text(task: dict) -> str:
	return (
		f"{TASK_MARK} The rule {task['rule']} has no value yet. Owner: {task['owner']}. "
		f"Waiting action: {task['action']}. The action stays closed until the owner decides."
	)


def open_owner_tasks(result: decision.Result) -> None:
	"""One open task per empty rule and action, for the system manager role (G-167)."""
	for task in result.owner_tasks:
		text = _task_text(task)
		if frappe.db.exists("ToDo", {"status": "Open", "description": text}):
			continue
		frappe.get_doc({"doctype": "ToDo", "status": "Open", "description": text, "role": TASK_ROLE}).insert(
			ignore_permissions=True
		)


def _judge(action_id: str, user: str) -> decision.Result:
	now = now_utc()
	result = _load_policy().evaluate(action_id, collect_evidence(user, now), now)
	if result.status == decision.CONFIGURATION_REQUIRED:
		open_owner_tasks(result)
	return result


def evaluate(action: object) -> dict:
	"""Decision for the signed-in user. Called by `platform_core.api.atonota_login.evaluate`."""
	user = _signed_in_user()
	if not isinstance(action, str) or not action or len(action) > MAX_ACTION_LENGTH:
		frappe.throw(
			_(
				"The action field must be a non-empty text of at most 140 characters.",
				context="platform_core.identity",
			),
			InvalidInput,
		)
	return _as_dict(_judge(action, user))


def _refuse(result: decision.Result) -> None:
	frappe.throw(
		_("The action {0} is not allowed now ({1}).", context="platform_core.identity").format(
			result.action, result.status
		),
		ActionRefused,
	)


def run_final_step[T](action_id: str, work: Callable[[], T]) -> T:
	"""Runs `work` only if the action is ready, and still ready at the final check (G-161).

	The final check loads the policy again and collects the evidence again. `Policy.confirm` refuses
	a result of another action, a changed policy and evidence that is gone. The caller must not hold
	pending writes: `PendingWrites` is raised before any decision.
	"""
	user = _signed_in_user()
	# A refusal below may commit the owner task. That commit must never make a caller's earlier
	# writes permanent, so the final step starts only in a clean transaction (AJA-264).
	if frappe.db.transaction_writes:
		frappe.throw(
			_(
				"A final step cannot run inside a transaction with pending writes.",
				context="platform_core.identity",
			),
			PendingWrites,
		)
	earlier = _judge(action_id, user)
	if earlier.status != decision.READY:
		if earlier.owner_tasks:
			# The refusal rolls the request back. The owner task must stay (G-167), so it is committed first.
			frappe.db.commit()  # nosemgrep: frappe-manual-commit
		_refuse(earlier)
	now = now_utc()
	final = _load_policy().confirm(earlier, action_id, collect_evidence(user, now), now)
	if final.status != decision.READY:
		reason = ", ".join(final.reasons) or final.status
		frappe.throw(
			_("The action {0} is not allowed now ({1}: {2}).", context="platform_core.identity").format(
				action_id, final.status, reason
			),
			ActionRefused,
		)
	return work()


def _create_paid_plan() -> dict:
	# The plan record and its price come with the price decision (G-166, K-61). Until then the gate
	# above never reaches this line, because the "paid-plan-pricing" rule has no value.
	frappe.throw(_("Paid plans are not available yet.", context="platform_core.identity"), ActionRefused)


def open_paid_plan() -> dict:
	"""Example final step: open a paid plan. Closed until the price decision (G-166)."""
	return run_final_step("open-paid-plan", _create_paid_plan)
