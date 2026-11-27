"""Home page summary of the signed-in user (AJA-1165).

Lists and counts apply Frappe document, row and field permissions.
Overlap pairs join two permission-filtered subqueries without loading all leaves into Python.
"""

import frappe
from frappe.query_builder.functions import Count
from frappe.utils import add_months, get_first_day, get_fullname, today

from hrms_tr.access import DOCTYPE

EMPLOYEE = "Employee"
# Each list is cut at this length. The counts still count every record.
LIST_LIMIT = 50
RECENT_LIMIT = 5
PENDING_FIELDS = [
	"name",
	"modified",
	"employee_name",
	"leave_type",
	"from_date",
	"to_date",
	"total_leave_days",
	"leave_balance",
]
# Open drafts and approved leaves take days off the team. Rejected and cancelled ones do not.
ACTIVE_FILTERS = [["status", "in", ["Open", "Approved"]], ["docstatus", "in", [0, 1]]]


def change_action(row) -> str:
	"""What the last change did to the leave application."""
	if row.docstatus == 2 or row.status == "Cancelled":
		return "cancelled"
	if row.docstatus == 1 and row.status in ("Approved", "Rejected"):
		return row.status.lower()
	if row.creation == row.modified:
		return "created"
	return "updated"


def _count(doctype: str, filters, field: str = "name") -> int:
	# The inner query stays in SQL. Grouping checks field permissions and counts distinct values.
	visible = frappe.qb.get_query(
		doctype,
		filters=filters,
		fields=[field],
		group_by=field,
		order_by=None,
		ignore_permissions=False,
	).as_("visible_records")
	rows = frappe.qb.from_(visible).select(Count("*").as_("total")).limit(1).run(as_dict=True)
	return int(rows[0].total) if rows else 0


def _pending() -> tuple[list[dict], int]:
	filters = {"leave_approver": frappe.session.user, "status": "Open", "docstatus": 0}
	rows = frappe.get_list(
		DOCTYPE,
		filters=filters,
		fields=PENDING_FIELDS,
		order_by="from_date asc, name asc",
		limit_page_length=LIST_LIMIT,
	)
	items = [
		{
			"name": row.name,
			"version": str(row.modified),
			"employee_name": row.employee_name,
			"leave_type": row.leave_type,
			"from_date": str(row.from_date) if row.from_date else None,
			"to_date": str(row.to_date) if row.to_date else None,
			"total_leave_days": row.total_leave_days,
			# Frappe leaves this field out when the user cannot read its level.
			"leave_balance": row.get("leave_balance"),
		}
		for row in rows
	]
	count = len(items) if len(items) < LIST_LIMIT else _count(DOCTYPE, filters)
	return items, count


def _overlap_problems() -> tuple[list[dict], int]:
	# These subqueries stay inside SQL. Only the bounded pairs and the aggregate reach Python.
	# Both sides use the same permission-filtered records, including field-level checks.
	visible = frappe.qb.get_query(
		DOCTYPE,
		filters=[*ACTIVE_FILTERS, ["to_date", ">=", today()], ["department", "is", "set"]],
		fields=["name", "employee_name", "department", "from_date", "to_date"],
		distinct=True,
		order_by=None,
		ignore_permissions=False,
	)
	first, second = visible.as_("first_leave"), visible.as_("second_leave")
	pairs = (
		frappe.qb.from_(first)
		.join(second)
		.on(
			(
				(first.from_date < second.from_date)
				| ((first.from_date == second.from_date) & (first.name < second.name))
			)
			& (first.department == second.department)
			& (first.from_date <= second.to_date)
			& (second.from_date <= first.to_date)
		)
	)
	counts = pairs.select(Count("*").as_("total")).limit(1).run(as_dict=True)
	rows = (
		pairs.select(
			first.department,
			first.name.as_("first_name"),
			first.employee_name.as_("first_employee_name"),
			first.from_date.as_("first_from_date"),
			first.to_date.as_("first_to_date"),
			second.name.as_("second_name"),
			second.employee_name.as_("second_employee_name"),
			second.from_date.as_("second_from_date"),
			second.to_date.as_("second_to_date"),
		)
		.orderby(first.department, first.from_date, first.name, second.from_date, second.name)
		.limit(LIST_LIMIT)
		.run(as_dict=True)
	)
	items = [
		{
			"kind": "overlap",
			"department": row.department,
			"leaves": [
				{
					"name": row[f"{side}_name"],
					"employee_name": row[f"{side}_employee_name"],
					"from_date": str(row[f"{side}_from_date"]),
					"to_date": str(row[f"{side}_to_date"]),
				}
				for side in ("first", "second")
			],
		}
		for row in rows
	]
	return items, int(counts[0].total) if counts else 0


def _employee_problems() -> tuple[list[dict], int]:
	# A user who cannot read employees sees no employee problem. The summary still answers.
	if not frappe.has_permission(EMPLOYEE, "read"):
		return [], 0
	filters = {"date_of_joining": ["is", "not set"]}
	rows = frappe.get_list(
		EMPLOYEE,
		filters=filters,
		fields=["name", "employee_name"],
		order_by="name asc",
		limit_page_length=LIST_LIMIT,
	)
	items = [
		{"kind": "missing_joining_date", "employee": row.name, "employee_name": row.employee_name}
		for row in rows
	]
	count = len(items) if len(items) < LIST_LIMIT else _count(EMPLOYEE, filters)
	return items, count


def _recent() -> list[dict]:
	rows = frappe.get_list(
		DOCTYPE,
		fields=["name", "employee_name", "status", "docstatus", "creation", "modified", "modified_by"],
		order_by="modified desc, name asc",
		limit_page_length=RECENT_LIMIT,
	)
	return [
		{
			"name": row.name,
			"employee_name": row.employee_name,
			"actor": get_fullname(row.modified_by),
			"action": change_action(row),
			"at": str(row.modified),
		}
		for row in rows
	]


def get_summary() -> dict:
	day = today()
	month_start = get_first_day(day)
	pending, pending_count = _pending()
	overlaps, overlap_count = _overlap_problems()
	employees, employee_count = _employee_problems()
	on_leave = _count(
		DOCTYPE,
		[
			["status", "=", "Approved"],
			["docstatus", "=", 1],
			["from_date", "<=", day],
			["to_date", ">=", day],
		],
		field="employee",
	)
	opened = _count(
		DOCTYPE,
		[["creation", ">=", str(month_start)], ["creation", "<", str(add_months(month_start, 1))]],
	)
	return {
		"pending_approvals": pending,
		"problems": (overlaps + employees)[:LIST_LIMIT],
		"recent_changes": _recent(),
		"counts": {
			"pending_approvals": pending_count,
			"on_leave_today": on_leave,
			"opened_this_month": opened,
			"problems": overlap_count + employee_count,
		},
	}
