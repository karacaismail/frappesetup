"""Manually started command that deletes log and proposal records past the retention period.

There is no scheduled job (D-6). The command starts in these three ways:

- `bench --site <site> execute platform_core.yapay_zeka.retention.purge --kwargs "{'older_than_days': 365}"`
- the `platform_core.api.ai.purge_logs` endpoint,
- the `purge_action_log` tool for AI. This way requires a preview and human approval.
"""

import frappe
from frappe import _

from platform_core.yapay_zeka import store
from platform_core.yapay_zeka.errors import CONTEXT

# Retention periods of the project record, personal data section.
# "AI Action Log" and "AI Usage Log": at least this many days.
MIN_DAYS = 365
# "AI Action Proposal": this many days after the decision or the expiry, whichever comes first.
PROPOSAL_DAYS = 30


def purge(older_than_days: int = MIN_DAYS, dry_run: bool = False) -> dict:
	"""Delete records past their retention period. If `dry_run` is true, only count (V-10).

	`older_than_days` is the period of the action log. The period of proposals is fixed.
	The usage log belongs to the model gateway, which applies its own 365 day rule.
	"""
	frappe.only_for("System Manager")
	days = int(older_than_days)
	if days < MIN_DAYS:
		frappe.throw(
			_("The retention period is at least {0} days.", context=CONTEXT).format(MIN_DAYS),
			frappe.ValidationError,
		)
	counts = store.purge_older_than(days, PROPOSAL_DAYS, delete=not dry_run)
	return {
		"dry_run": bool(dry_run),
		"older_than_days": days,
		"proposal_days": PROPOSAL_DAYS,
		**counts,
		"usage_logs": _purge_usage_logs(bool(dry_run)),
	}


def _purge_usage_logs(dry_run: bool) -> int | None:
	"""Start the model gateway's own command for the "AI Usage Log". Return the number of records.

	The gateway owns that log and its 365 day rule. Its command deletes in batches, so a large
	backlog needs more than one run. None means the gateway refused or is not installed.
	"""
	try:
		# The gateway's public endpoint module. It is looked up at call time.
		from platform_core.api.model import purge_usage
	except ImportError:
		return None
	status = frappe.local.response.get("http_status_code")
	result = purge_usage(dry_run=dry_run)
	if not isinstance(result, dict) or "error" in result:
		# The gateway reports a refusal through the response status. This command's own answer stands.
		frappe.local.response["http_status_code"] = status
		if status is None:
			frappe.local.response.pop("http_status_code", None)
		return None
	return int(result["eligible"] if dry_run else result["deleted"])
