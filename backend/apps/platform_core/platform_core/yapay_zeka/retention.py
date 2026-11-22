"""Manually started command that deletes log and proposal records past the retention period.

There is no scheduled job (D-6). The command starts in these three ways:

- in the bench folder: `bench --site <site> execute platform_core.yapay_zeka.retention.purge --kwargs "{'older_than_days': 365, 'dry_run': False}"`.
  Without `dry_run` the command only counts.
- the `platform_core.api.ai.purge_logs` endpoint,
- the `purge_action_log` tool for AI. This way requires a preview and human approval.
"""

import hashlib
import inspect
import json
import secrets

import frappe
from frappe import _

from platform_core.yapay_zeka import access, store
from platform_core.yapay_zeka.errors import CONTEXT, log_tool_error

# Retention periods of the project record, personal data section.
# "AI Action Log" and "AI Usage Log": at least this many days.
MIN_DAYS = 365
# "AI Action Proposal": this many days after the decision or the expiry, whichever comes first.
PROPOSAL_DAYS = 30
# Upper bound of the period a caller may ask for. A larger number has no use and overflows dates.
MAX_DAYS = 36_500
# Records of each kind one run deletes at most. Each delete loads its document, so a run is bounded.
BATCH_SIZE = 500
# A web delete needs the confirmation of a preview. The confirmation lives this long and works once.
CONFIRMATION_SECONDS = 600
CONFIRMATION_KEY = "yz_purge_confirmation:"
MAX_TOKEN_CHARS = 128


def _days(older_than_days: object) -> int:
	"""The retention period of the action log as a number within its bounds."""
	if isinstance(older_than_days, bool) or not isinstance(older_than_days, int | str):
		older_than_days = -1
	try:
		days = int(older_than_days)
	except ValueError:
		days = -1
	if not MIN_DAYS <= days <= MAX_DAYS:
		frappe.throw(
			_("The retention period is between {0} and {1} days.", context=CONTEXT).format(
				MIN_DAYS, MAX_DAYS
			),
			frappe.ValidationError,
		)
	return days


def purge(older_than_days: int = MIN_DAYS, dry_run: bool = True, selection: dict | None = None) -> dict:
	"""Delete records past their retention period. If `dry_run` is true, only count (V-10).

	`older_than_days` is the period of the action log. The period of proposals is fixed.
	The usage log belongs to the model gateway, which applies its own 365 day rule.
	With `selection` exactly those records are deleted. Without it the records are chosen once,
	here, and those are deleted. A record is never chosen a second time between count and delete.

	A delete is all or nothing. The gateway deletes its chosen usage records first, all of them
	or none. If it refuses, its error goes to the caller and nothing of this layer is deleted.
	"""
	frappe.only_for("System Manager")
	days = _days(older_than_days)
	chosen = selection or _choose(days)
	usage = dict(chosen["usage"])
	if not dry_run:
		if chosen["usage_names"] is not None:
			usage["deleted"] = _delete_usage_logs(chosen["usage_names"])
		# Exactly the chosen records go. Nothing is chosen a second time.
		store.delete_selected(chosen["logs"], chosen["proposals"])
	return {
		"dry_run": bool(dry_run),
		"older_than_days": days,
		"proposal_days": PROPOSAL_DAYS,
		"batch_size": BATCH_SIZE,
		"logs": len(chosen["logs"]),
		"logs_waiting": chosen["logs_waiting"],
		"proposals": len(chosen["proposals"]),
		"proposals_waiting": chosen["proposals_waiting"],
		"usage_logs": usage,
	}


def _choose(days: int) -> dict:
	"""Choose the records of one delete run: this layer's own and the gateway's usage records."""
	usage, usage_names = _preview_usage_logs()
	return {
		**store.select_expired(days, PROPOSAL_DAYS, BATCH_SIZE),
		"usage": usage,
		"usage_names": usage_names,
	}


def select(older_than_days: int = MIN_DAYS) -> tuple[dict, dict, str]:
	"""Preview a delete: the counts a human reads, the records chosen and a digest of both.

	The digest covers every chosen name, the usage records included, and every number of the
	preview. A confirmation or an approval is bound to it, so it is valid only for that preview.
	"""
	frappe.only_for("System Manager")
	days = _days(older_than_days)
	chosen = _choose(days)
	counted = purge(days, dry_run=True, selection=chosen)
	bound = [
		days,
		chosen["logs"],
		chosen["proposals"],
		chosen["logs_waiting"],
		chosen["proposals_waiting"],
		chosen["usage"],
		chosen["usage_names"],
	]
	return counted, chosen, hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()


def purge_from_web(
	older_than_days: int = MIN_DAYS, dry_run: bool = True, confirmation_token: str | None = None
) -> dict:
	"""The web endpoint's way in: a delete needs the confirmation of a preview, and only once.

	The counting call is the preview. It returns a confirmation token that lives for
	`CONFIRMATION_SECONDS`. The delete call must carry it. The token is bound to the user, the
	period and the previewed numbers, and it is claimed in one step, so it works once.
	A preview whose numbers have changed since is refused: the human confirmed other numbers.
	"""
	# The role comes first. A caller without it learns nothing about tokens.
	frappe.only_for("System Manager")
	if dry_run:
		counted, chosen, digest = select(older_than_days)
		token = secrets.token_urlsafe(32)
		kept = {"user": frappe.session.user, "digest": digest, "selection": chosen}
		frappe.cache.set_value(_confirmation_key(token, "data"), kept, expires_in_sec=CONFIRMATION_SECONDS)
		frappe.cache.set_value(_confirmation_key(token, "claim"), 1, expires_in_sec=CONFIRMATION_SECONDS)
		return {**counted, "confirmation_token": token}
	refusal = access.PreviewRequired(
		_("Ask for a preview first, then send its confirmation token. Nothing was deleted.", context=CONTEXT)
	)
	if not isinstance(confirmation_token, str) or not 0 < len(confirmation_token) <= MAX_TOKEN_CHARS:
		raise refusal
	kept = frappe.cache.get_value(_confirmation_key(confirmation_token, "data"))
	# The claim is one atomic step, so a token works once even if two requests race.
	claimed = frappe.cache.getdel(frappe.cache.make_key(_confirmation_key(confirmation_token, "claim")))
	frappe.cache.delete_value(_confirmation_key(confirmation_token, "data"))
	if kept is None or claimed is None or kept["user"] != frappe.session.user:
		raise refusal
	# Every number of the preview must still hold: the chosen records and all that wait.
	_counted, _chosen, digest = select(older_than_days)
	if digest != kept["digest"]:
		raise refusal
	try:
		return purge(older_than_days, dry_run=False, selection=kept["selection"])
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as error:
		# A chosen record of this layer or of the gateway is no longer eligible. The gateway
		# deletes all or none, and this rollback undoes whatever else the request did.
		frappe.db.rollback()
		frappe.clear_messages()
		log_tool_error("purge_logs", error)
		raise refusal from None


def _confirmation_key(token: str, part: str) -> str:
	"""Cache key of a confirmation. It holds a digest, never the token itself."""
	return f"{CONFIRMATION_KEY}{part}:{hashlib.sha256(token.encode()).hexdigest()}"


def _gateway_purge():
	"""The gateway's shared function and whether it takes the names to delete (contract, section 10)."""
	import platform_core.model_gecidi.api as gateway

	purge = getattr(gateway, "purge_usage_logs", None)
	takes_names = purge is not None and "names" in inspect.signature(purge).parameters
	return purge, takes_names


def _preview_usage_logs() -> tuple[dict, list[str] | None]:
	"""Ask the gateway which usage records one run would delete. Nothing is deleted.

	The gateway owns the "AI Usage Log". Its function `purge_usage_logs(*, dry_run, names)` checks
	the caller's permission itself and applies the 365 days of the project record, from the web
	and from the command line alike. The counting call returns the names it would delete.

	Returns what a human reads and the chosen names. The first is `ok` with the counts,
	`not_run` with a reason, or `error` with the error type. It is never empty. The names are
	None unless the status is `ok`: then no delete call is made.
	An older gateway without `names` would choose its own records at delete time. It is not used.
	"""
	purge, takes_names = _gateway_purge()
	if purge is None:
		return {"status": "not_run", "reason": "gateway_purge_unavailable"}, None
	if not takes_names:
		return {"status": "not_run", "reason": "gateway_purge_outdated"}, None
	try:
		result = purge(dry_run=True)
		names = [str(name) for name in result["names"]]
		# `eligible` is what waits. `to_delete` is what this run takes. `deleted` is what it took.
		usage = {"status": "ok", "eligible": int(result["eligible"]), "to_delete": len(names), "deleted": 0}
		return usage, names
	except Exception as error:
		# The text of the gateway's error may carry a value. Only its type is returned.
		log_tool_error("purge_usage_logs", error)
		frappe.clear_messages()
		return {"status": "error", "reason": type(error).__name__}, None


def _delete_usage_logs(names: list[str]) -> int:
	"""Have the gateway delete exactly the chosen usage records. Return how many it deleted.

	The gateway checks the records again under a lock and deletes all of them or none. Its
	error is not caught here: the caller must not go on and must not report a delete.
	"""
	purge, _takes_names = _gateway_purge()
	return int(purge(dry_run=False, names=list(names))["deleted"])
