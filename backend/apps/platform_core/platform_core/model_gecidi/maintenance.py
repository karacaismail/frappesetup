"""Human-operated usage reconciliation and retention."""

import re
from datetime import timedelta
from decimal import Decimal
from secrets import token_hex
from uuid import uuid4

import frappe
from frappe.utils import now_datetime

from platform_core.model_gecidi import gateway, ledger, policy
from platform_core.model_gecidi.doctype.ai_api.ai_api import clear_api_credential as clear_credential

DEFAULT_RETENTION_DAYS = 365
DELETE_BATCH_SIZE = 500
PREVIEW_TTL_SECONDS = 300
USAGE_LOG = "AI Usage Log"


def _cost(value):
	if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,11})(?:[.][0-9]{1,9})?", value):
		raise policy.Denied(400, "invalid_cost")
	return Decimal(value)


def _usage_log(name, *, for_update=False):
	if not isinstance(name, str) or not 0 < len(name) <= 140:
		raise policy.Denied(400, "invalid_request")
	try:
		return frappe.get_doc(USAGE_LOG, name, for_update=for_update)
	except frappe.DoesNotExistError:
		raise frappe.PermissionError from None


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


def _pending_cutoff():
	return now_datetime() - timedelta(seconds=gateway.STALE_ATTEMPT_SECONDS)


def preview_pending_recovery(name):
	"""Load an eligible, readable reservation for a single-record approval."""
	policy.require_user(managers_only=True)
	log = _usage_log(name)
	log.check_permission("read")
	if log.result != "pending" or log.attempted_at > _pending_cutoff():
		raise frappe.ValidationError
	return log


def reconcile_stale_pending(*, name=None):
	"""Close a batch, or just the record named in an AI approval."""
	policy.require_user(managers_only=True)
	filters = {"result": "pending", "attempted_at": ["<=", _pending_cutoff()]}
	if name is not None:
		filters["name"] = name
	targets = frappe.qb.get_query(
		USAGE_LOG,
		filters=filters,
		fields=["name"],
		order_by="attempted_at asc, name asc",
		limit=DELETE_BATCH_SIZE,
		for_update=True,
	).run(pluck=True)
	if targets:
		# The locking read excludes attempts already settled by the request owner.
		# A late finisher will only update rows whose result is still pending.
		frappe.db.set_value(
			USAGE_LOG,
			{**filters, "name": ["in", targets]},
			{"result": "unknown", "failure_code": "pending_recovery"},
		)
	return {"closed": len(targets), "targets": targets}


def _purge_batch(filters, *, for_update=False):
	return frappe.qb.get_query(
		USAGE_LOG,
		filters=filters,
		fields=["name", "modified"],
		order_by="attempted_at asc, name asc",
		limit=DELETE_BATCH_SIZE,
		for_update=for_update,
	).run(as_dict=True)


def _purge_preview_key(token):
	return f"model_gateway:purge_preview:{token}"


def purge_usage(dry_run=True, preview_token=None):
	policy.require_user(managers_only=True)
	if type(dry_run) is not bool or (dry_run and preview_token is not None):
		raise policy.Denied(400, "invalid_request")
	if not dry_run:
		if preview_token is None:
			raise policy.Denied(400, "preview_required")
		if not isinstance(preview_token, str) or not re.fullmatch(r"[0-9a-f]{64}", preview_token):
			raise policy.Denied(409, "preview_invalid")
		key = _purge_preview_key(preview_token)
		preview = frappe.cache.get_value(key, expires=True, use_local_cache=False)
		if not preview or preview["user"] != frappe.session.user:
			raise policy.Denied(409, "preview_invalid")
	days = frappe.conf.get("model_gateway_usage_retention_days", DEFAULT_RETENTION_DAYS)
	if type(days) is not int or not 32 <= days <= 36500:
		raise policy.Denied(503, "invalid_retention")
	now = now_datetime()
	cutoff = now - timedelta(days=days) if dry_run else preview["cutoff"]
	filters = {
		"attempted_at": ["<", cutoff],
		"result": ["not in", ledger.UNSETTLED],
	}
	rows = _purge_batch(filters, for_update=not dry_run)
	batch = [(row.name, row.modified) for row in rows]
	targets = [name for name, _ in batch]
	eligible = frappe.db.count(USAGE_LOG, filters)
	deleted = 0
	if dry_run:
		preview_token = token_hex(32)
		frappe.cache.set_value(
			_purge_preview_key(preview_token),
			{"user": frappe.session.user, "days": days, "cutoff": cutoff, "batch": batch},
			expires_in_sec=PREVIEW_TTL_SECONDS,
		)
	else:
		if preview["days"] != days or preview["batch"] != batch:
			raise policy.Denied(409, "preview_invalid")
		# Claim at most once, including empty batches with no database rows to lock.
		if frappe.cache.getdel(frappe.cache.make_key(key)) is None:
			raise policy.Denied(409, "preview_invalid")
		for name in targets:
			# The gateway operation checks manager permissions before taking the row locks.
			# O-32: retention never leaves a Deleted Document copy.
			frappe.delete_doc(  # nosemgrep: frappe-ignore-permissions
				USAGE_LOG, name, ignore_permissions=True, ignore_missing=False, delete_permanently=True
			)
		deleted = len(targets)
		# The management operation writes a fixed audit record in the same transaction.
		frappe.get_doc(
			{
				"doctype": "Activity Log",
				"name": uuid4().hex,
				"reference_doctype": USAGE_LOG,
				"subject": "Model gateway usage logs purged",
				"content": f"Deleted usage records: {deleted}",
				"status": "Success",
				"user": frappe.session.user,
				"communication_date": now,
			}
		).db_insert()
		preview_token = None
	return {
		"eligible": eligible,
		"deleted": deleted,
		"dry_run": dry_run,
		"targets": targets,
		"preview_token": preview_token,
	}


def clear_api_credential(api):
	policy.require_user(managers_only=True)
	target = gateway._document("AI API", api)
	clear_credential(target.name)
	target.add_comment("Info", "Model gateway API credential cleared.")
	return {"name": target.name, "cleared": True}
