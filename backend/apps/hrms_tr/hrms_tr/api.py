"""HTTP entry points for leave application actions."""

from typing import Annotated, TypedDict

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from pydantic import StringConstraints

from hrms_tr import home_summary, leave
from hrms_tr.leave import LeaveName, LeaveVersion


# leave.approve locks the target and checks its read, write, and submit rights.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
@rate_limit(limit=60, seconds=60, methods=["POST"], ip_based=False, user_based=True)
def approve_leave(name: LeaveName | None = None, version: LeaveVersion | None = None) -> dict[str, str]:
	if name is None:
		frappe.throw(_("Select a leave application.", context="hrms_tr"), frappe.ValidationError)
	if version is None:
		frappe.throw(
			_("Read the leave application version before approving.", context="hrms_tr"),
			frappe.ValidationError,
		)
	return leave.approve(name, expected_version=version)


# leave.reject locks the target and checks its read, write, and submit rights.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
@rate_limit(limit=60, seconds=60, methods=["POST"], ip_based=False, user_based=True)
def reject_leave(name: LeaveName | None = None, version: LeaveVersion | None = None) -> dict[str, str]:
	if name is None:
		frappe.throw(_("Select a leave application.", context="hrms_tr"), frappe.ValidationError)
	if version is None:
		frappe.throw(
			_("Read the leave application version before rejecting.", context="hrms_tr"),
			frappe.ValidationError,
		)
	return leave.reject(name, expected_version=version)


# leave.cancel locks the target and checks HR, read, and cancel permissions.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
@rate_limit(limit=60, seconds=60, methods=["POST"], ip_based=False, user_based=True)
def cancel_leave(name: LeaveName | None = None, version: LeaveVersion | None = None) -> dict[str, str]:
	if name is None:
		frappe.throw(_("Select a leave application.", context="hrms_tr"), frappe.ValidationError)
	if version is None:
		frappe.throw(
			_("Read the leave application version before cancelling.", context="hrms_tr"),
			frappe.ValidationError,
		)
	return leave.cancel(name, expected_version=version)


# The HRMS lookup checks the caller's access to this employee before returning the approver.
@frappe.whitelist(methods=["GET"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def get_leave_approver(
	employee: Annotated[str, StringConstraints(min_length=1, max_length=140)] | None = None,
) -> dict[str, str | None]:
	if employee is None:
		frappe.throw(_("Select an employee.", context="hrms_tr"), frappe.ValidationError)
	return {"approver": leave.get_approver(employee)}


class LeaveRequestSources(TypedDict):
	"""Record types supplying the available request defaults."""

	employee: str | None
	employee_name: str | None
	leave_type: str | None
	leave_balance: str | None


class LeaveRequestContext(TypedDict):
	"""Minimal self-service data for a new leave application."""

	employee: str | None
	employee_name: str | None
	leave_type: str | None
	leave_balance: float | None
	sources: LeaveRequestSources


# The employee filter is bound to the session, never request input. HRMS also checks balance access.
@frappe.whitelist(methods=["GET"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
def get_leave_request_context(
	leave_type: Annotated[str, StringConstraints(min_length=1, max_length=140)] | None = None,
) -> LeaveRequestContext:
	"""Return available defaults for the signed-in employee, without inventing missing data."""
	from frappe.utils import today

	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Not permitted", context="hrms_tr"), frappe.PermissionError)

	sources: LeaveRequestSources = {
		"employee": None,
		"employee_name": None,
		"leave_type": None,
		"leave_balance": None,
	}
	result: LeaveRequestContext = {
		"employee": None,
		"employee_name": None,
		"leave_type": None,
		"leave_balance": None,
		"sources": sources,
	}
	# Portal employees need no broad Employee read permission to read these two own fields.
	employee = frappe.db.get_value(
		"Employee", {"user_id": user, "status": "Active"}, ["name", "employee_name"], as_dict=True
	)
	if not employee:
		return result

	result["employee"] = employee.name
	sources["employee"] = "Employee"
	result["employee_name"] = employee.employee_name or None
	if result["employee_name"] is not None:
		sources["employee_name"] = "Employee"

	date = today()
	if leave_type is not None:
		selected_type = leave_type
		if not frappe.db.exists("Leave Type", selected_type):
			return result
		sources["leave_type"] = "Leave Type"
	else:
		# Self-service access is limited to the employee resolved from this session above.
		allocated_types = frappe.get_all(
			"Leave Allocation",
			filters={
				"employee": employee.name,
				"docstatus": 1,
				"from_date": ["<=", date],
				"to_date": [">=", date],
			},
			pluck="leave_type",
			distinct=True,
			order_by="leave_type",
			limit_page_length=2,
		)
		if len(allocated_types) != 1:
			return result
		selected_type = allocated_types[0]
		sources["leave_type"] = "Leave Allocation"
	result["leave_type"] = selected_type
	native_module = "hrms.hr.doctype.leave_application.leave_application"
	get_leave_allocation_records = frappe.get_attr(f"{native_module}.get_leave_allocation_records")
	get_leave_balance_on = frappe.get_attr(f"{native_module}.get_leave_balance_on")
	# HRMS returns zero without an allocation. Preserve the distinction between absent data and zero.
	if selected_type not in get_leave_allocation_records(employee.name, date, selected_type):
		return result
	result["leave_balance"] = get_leave_balance_on(employee.name, selected_type, date)
	if result["leave_balance"] is not None:
		sources["leave_balance"] = "Leave Ledger Entry"
	return result


# home_summary uses permission-filtered lists and query-builder reads for both items and counts.
@frappe.whitelist(methods=["GET"])  # nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
@rate_limit(limit=120, seconds=60, methods=["GET"], ip_based=False, user_based=True)
def get_home_summary() -> dict:
	return home_summary.get_summary()
