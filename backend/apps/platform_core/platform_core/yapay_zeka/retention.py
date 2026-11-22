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

MIN_DAYS = 365


def purge(older_than_days: int = MIN_DAYS, dry_run: bool = False) -> dict:
	"""Delete old records. If `dry_run` is true, only count (V-10).

	Proposals with an unknown result are not deleted. A human closes them first.
	"""
	frappe.only_for("System Manager")
	days = int(older_than_days)
	if days < MIN_DAYS:
		frappe.throw(
			_("The retention period is at least {0} days.", context=CONTEXT).format(MIN_DAYS),
			frappe.ValidationError,
		)
	logs, proposals = store.purge_older_than(days, delete=not dry_run)
	return {"dry_run": bool(dry_run), "older_than_days": days, "logs": logs, "proposals": proposals}
