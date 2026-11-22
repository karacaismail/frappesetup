"""Manual cleanup for the mobile event log and operation receipts."""

from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from .protocol import MobileError
from .store import SEQUENCE_DOCTYPE, SEQUENCE_NAME

CLEANUP_LIMIT = 1000
DEFAULT_RETENTION_DAYS = 30


def _cutoff(setting, now):
	days = frappe.conf.get(setting, DEFAULT_RETENTION_DAYS)
	if type(days) is not int or not 1 <= days <= 3650:
		raise MobileError("invalid_retention_setting", 503)
	return now - timedelta(days=days)


def _eligible(doctype, filters, fields, *, for_update):
	return frappe.db.get_values(
		doctype,
		filters,
		fields,
		as_dict=True,
		order_by="creation asc, name asc",
		limit=CLEANUP_LIMIT,
		for_update=for_update,
	)


def cleanup(dry_run=False):
	"""Preview or remove one bounded batch. Bench or the HTTP request owns the transaction."""
	if type(dry_run) is not bool:
		raise MobileError("invalid_request")

	now = now_datetime()
	operation_cutoff = _cutoff("mobile_operation_retention_days", now)
	upsert_cutoff = _cutoff("mobile_upsert_retention_days", now)
	removal_cutoff = _cutoff("mobile_removal_retention_days", now)
	operations = _eligible(
		"Mobile Operation",
		{"creation": ["<", operation_cutoff]},
		["name"],
		for_update=not dry_run,
	)
	if operations and not dry_run:
		frappe.db.delete("Mobile Operation", {"name": ["in", [row.name for row in operations]]})

	floor = frappe.db.get_value(SEQUENCE_DOCTYPE, SEQUENCE_NAME, "retention_floor", for_update=not dry_run)
	if floor is None:
		raise MobileError("mobile_schema_unavailable", 503)
	changes = []
	for kind, cutoff in (("remove", removal_cutoff), ("upsert", upsert_cutoff)):
		changes.extend(
			_eligible(
				"Mobile Change",
				{"kind": kind, "creation": ["<", cutoff]},
				["name", "sequence"],
				for_update=not dry_run,
			)
		)
	if changes and not dry_run:
		frappe.db.delete("Mobile Change", {"name": ["in", [row.name for row in changes]]})
		floor = max(floor, *(row.sequence for row in changes))
		frappe.db.set_value(SEQUENCE_DOCTYPE, SEQUENCE_NAME, "retention_floor", floor)
	return {
		"dry_run": dry_run,
		"removed": 0 if dry_run else len(changes),
		"operations_removed": 0 if dry_run else len(operations),
		"eligible_changes": len(changes),
		"eligible_operations": len(operations),
	}
