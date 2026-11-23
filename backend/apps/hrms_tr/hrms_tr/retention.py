"""Manually remove expired HRMS TR leave records."""

from datetime import date

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import getdate, today


def purge(*, dry_run: bool = True, limit: int = 500) -> dict[str, bool | int | str]:
	"""Count eligible records, or purge them in one bench transaction."""
	frappe.only_for("System Manager")
	if not isinstance(dry_run, bool):
		frappe.throw(_("Use a boolean for dry_run.", context="hrms_tr"), frappe.ValidationError)
	if type(limit) is not int or limit <= 0:
		frappe.throw(_("Use a positive integer for limit.", context="hrms_tr"), frappe.ValidationError)
	days = frappe.conf.get("hrms_tr_retention_days")
	if type(days) is not int or days <= 0:
		frappe.throw(
			_("Set a valid hrms_tr_retention_days site value.", context="hrms_tr"), frappe.ValidationError
		)
	ordinal = getdate(today()).toordinal() - days
	if ordinal < 1:
		frappe.throw(
			_("The configured retention period exceeds the supported date range.", context="hrms_tr"),
			frappe.ValidationError,
		)
	cutoff = date.fromordinal(ordinal)
	applications = frappe.qb.DocType("Leave Application")
	employees = frappe.qb.DocType("Employee")
	# Native cancellation changes the leave ledger and attendance. Leave submitted records alone.
	eligible = (
		frappe.qb.from_(applications)
		.join(employees)
		.on(employees.name == applications.employee)
		.where(
			(employees.status == "Left")
			& (employees.relieving_date < cutoff)
			& (applications.to_date < cutoff)
			& (applications.docstatus.isin((0, 2)))
		)
	)
	total = eligible.select(Count(applications.name)).run()[0][0]
	if dry_run:
		processed = min(total, limit)
	else:
		batch = eligible.select(applications.name).orderby(applications.name).limit(limit).for_update().run()
		for (name,) in batch:
			frappe.delete_doc("Leave Application", name, delete_permanently=True)
		processed = len(batch)
	return {
		"dry_run": dry_run,
		"cutoff": cutoff.isoformat(),
		"leaves": processed,
		"remaining": total - processed,
	}
