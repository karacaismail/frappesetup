"""Manually remove expired HRMS TR employment and leave records."""

from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate, today


def purge(*, dry_run: bool = True) -> dict[str, bool | int | str]:
	"""Count eligible records, or purge them in one bench transaction."""
	frappe.only_for("System Manager")
	if not isinstance(dry_run, bool):
		frappe.throw(_("Use a boolean for dry_run."), frappe.ValidationError)
	days = frappe.conf.get("hrms_tr_retention_days")
	if type(days) is not int or days <= 0:
		frappe.throw(_("Set a valid hrms_tr_retention_days site value."), frappe.ValidationError)
	ordinal = getdate(today()).toordinal() - days
	if ordinal < 1:
		frappe.throw(
			_("The configured retention period exceeds the supported date range."), frappe.ValidationError
		)
	cutoff = date.fromordinal(ordinal)
	employee_names = frappe.get_all(
		"Employee",
		filters={"status": "Left", "relieving_date": ["<", cutoff.isoformat()]},
		pluck="name",
		order_by="name asc",
	)
	employees = leaves = 0
	for name in employee_names:
		employee = frappe.get_doc("Employee", name, for_update=not dry_run)
		if (
			employee.status != "Left"
			or not employee.relieving_date
			or getdate(employee.relieving_date) >= cutoff
		):
			continue
		leave_rows = frappe.qb.get_query(
			"Leave Application",
			fields=["name"],
			filters={"employee": name},
			order_by="name asc",
			for_update=not dry_run,
		).run(as_dict=True)
		applications = [
			frappe.get_doc("Leave Application", row["name"], for_update=not dry_run) for row in leave_rows
		]
		if any(
			doc.employee != name or not doc.to_date or getdate(doc.to_date) >= cutoff for doc in applications
		):
			continue
		if not dry_run:
			for doc in applications:
				if doc.docstatus == 1:
					doc.cancel()
				frappe.delete_doc("Leave Application", doc.name, delete_permanently=True)
			frappe.delete_doc("Employee", name, delete_permanently=True)
		employees += 1
		leaves += len(applications)
	return {"dry_run": dry_run, "cutoff": cutoff.isoformat(), "employees": employees, "leaves": leaves}
