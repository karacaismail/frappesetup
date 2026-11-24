"""HTTP entry points for leave application actions."""

from typing import Annotated

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from pydantic import StringConstraints

from hrms_tr import leave
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
