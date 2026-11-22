"""Human-operated usage reconciliation and retention."""

import re
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import frappe
from frappe.utils import now_datetime

from platform_core.model_gecidi import gateway, ledger, policy
from platform_core.model_gecidi.doctype.ai_api.ai_api import clear_api_credential as clear_credential

DEFAULT_RETENTION_DAYS = 365
DELETE_BATCH_SIZE = 500


def _cost(value):
	if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,11})(?:[.][0-9]{1,9})?", value):
		raise policy.Denied(400, "invalid_cost")
	return Decimal(value)


def _usage_log(name, *, for_update=False):
	if not isinstance(name, str) or not 0 < len(name) <= 140:
		raise policy.Denied(400, "invalid_request")
	try:
		return frappe.get_doc("AI Usage Log", name, for_update=for_update)
	except frappe.DoesNotExistError:
		raise policy.Denied(403, "permission_denied") from None


def resolve_usage(log, cost, currency, note=None):
	policy.require_user(managers_only=True)
	verified_cost = _cost(cost)
	if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
		raise policy.Denied(400, "invalid_currency")
	if note is None:
		note = ""
	if not isinstance(note, str) or len(note) > 240 or (note and not note.isprintable()):
		raise policy.Denied(400, "invalid_note")
	initial = _usage_log(log)
	initial.check_permission("read")
	with gateway.scoped_lock("account", initial.account):
		frappe.db.commit()  # nosemgrep
		gateway.lock_row("AI Account", initial.account, ("name",))
		current = _usage_log(log, for_update=True)
		if currency != current.currency:
			raise policy.Denied(400, "currency_mismatch")
		if current.result == "pending":
			# A live attempt may still settle. Reconcile only after its lease is stale.
			if current.attempted_at > now_datetime() - timedelta(seconds=gateway.STALE_ATTEMPT_SECONDS):
				raise policy.Denied(409, "attempt_in_progress")
		elif current.result not in ledger.UNSETTLED and (current.result != "success" or current.cost_known):
			raise policy.Denied(409, "attempt_already_settled")
		frappe.db.set_value(
			"AI Usage Log",
			log,
			{
				"result": "resolved",
				"cost": verified_cost,
				"cost_known": 1,
				"resolved_by": frappe.session.user,
				"resolved_at": now_datetime(),
				"previous_result": current.result,
				"resolution_note": note.strip() or "Cost verified by a manager.",
			},
		)
		# Commit before releasing the account lock so a new reservation sees the cost.
		frappe.db.commit()  # nosemgrep
	return {"name": log, "result": "resolved", "cost": format(verified_cost, "f"), "currency": currency}


def purge_usage(dry_run=True):
	policy.require_user(managers_only=True)
	if type(dry_run) is not bool:
		raise policy.Denied(400, "invalid_request")
	days = frappe.conf.get("model_gateway_usage_retention_days", DEFAULT_RETENTION_DAYS)
	if type(days) is not int or not 32 <= days <= 36500:
		raise policy.Denied(503, "invalid_retention")
	filters = {
		"attempted_at": ["<", now_datetime() - timedelta(days=days)],
		"result": ["not in", ledger.UNSETTLED],
	}
	eligible = frappe.db.count("AI Usage Log", filters)
	deleted = 0
	if not dry_run:
		names = frappe.get_all(
			"AI Usage Log",
			filters=filters,
			order_by="attempted_at asc",
			limit=DELETE_BATCH_SIZE,
			pluck="name",
		)
		if names:
			frappe.db.delete("AI Usage Log", {**filters, "name": ["in", names]})
			deleted = len(names)
		# The management operation writes a fixed audit record in the same transaction.
		frappe.get_doc(
			{
				"doctype": "Activity Log",
				"name": uuid4().hex,
				"reference_doctype": "AI Usage Log",
				"subject": "Model gateway usage logs purged",
				"content": f"Deleted usage records: {deleted}",
				"status": "Success",
				"user": frappe.session.user,
				"communication_date": now_datetime(),
			}
		).db_insert()
	return {"eligible": eligible, "deleted": deleted, "dry_run": dry_run}


def clear_api_credential(api):
	policy.require_user(managers_only=True)
	target = gateway._document("AI API", api)
	clear_credential(target.name)
	target.add_comment("Info", "Model gateway API credential cleared.")
	return {"name": target.name, "cleared": True}
