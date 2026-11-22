"""Use Frappe and HRMS permissions and validation for leave approvals."""

from typing import Annotated

import frappe
from frappe import _
from frappe.model.docstatus import DocStatus
from pydantic import StringConstraints

from hrms_tr.access import DOCTYPE

HR_ROLE = "HRMS TR Admin"
MANAGER_ROLE = "HRMS TR Manager"
APPROVER_ROLES = (MANAGER_ROLE, HR_ROLE)
OPERATIONS_ROLES = ("System Manager", "HR Manager")
HRMS_APPROVER_METHOD = "hrms.hr.doctype.leave_application.leave_application.get_leave_approver"

LeaveName = Annotated[str, StringConstraints(min_length=1, max_length=140)]
LeaveVersion = Annotated[str, StringConstraints(min_length=1, max_length=40)]


def check_approver_role():
	if not set((*APPROVER_ROLES, *OPERATIONS_ROLES)).intersection(frappe.get_roles()):
		frappe.throw(_("You do not have permission to approve leave."), frappe.PermissionError)


def check_not_own_leave(doc):
	if frappe.db.get_value("Employee", doc.employee, "user_id") == frappe.session.user:
		frappe.throw(_("You cannot approve your own leave."), frappe.PermissionError)


def check_hr_role():
	if frappe.session.user != "Administrator" and HR_ROLE not in frappe.get_roles():
		frappe.throw(_("Only HRMS TR Admin can amend leave applications."), frappe.PermissionError)


def validate_cancellation(doc, method=None):
	if frappe.session.user == "Administrator":
		return
	roles = frappe.get_roles()
	if set(OPERATIONS_ROLES).intersection(roles):
		return
	if HR_ROLE not in roles or not doc.flags.hrms_tr_version_checked:
		frappe.throw(_("You do not have permission to cancel leave."), frappe.PermissionError)


def validate_manager_fields(doc, method=None):
	"""Restrict team drafts to status edits for managers."""
	before = doc.get_doc_before_save()
	if before is None or frappe.session.user == "Administrator":
		return
	roles = set(frappe.get_roles())
	if MANAGER_ROLE not in roles or roles.intersection((HR_ROLE, *OPERATIONS_ROLES)):
		return
	if frappe.db.get_value("Employee", before.employee, "user_id") == frappe.session.user:
		return
	# Frappe sets these audit columns before validation. The manager cannot set their values.
	# get_valid_columns checks parent fields. Leave Application currently has no writable child table.
	status_and_audit_fields = {"status", "docstatus", "modified", "modified_by"}
	protected_fields = set(doc.meta.get_valid_columns()) - status_and_audit_fields
	if any(doc.has_value_changed(fieldname) for fieldname in protected_fields):
		frappe.throw(
			_("Managers can only change the status of a team leave application."), frappe.PermissionError
		)


def validate_approval(doc, method=None):
	"""Apply the approval policy to native Frappe writes."""
	if not doc.is_new() and doc.has_value_changed("employee"):
		frappe.throw(_("The employee cannot change on a saved leave application."))
	if doc.is_new() and doc.amended_from:
		check_hr_role()
		if frappe.db.get_value(DOCTYPE, doc.amended_from, "employee") != doc.employee:
			frappe.throw(_("The employee cannot change on an amended leave application."))
	if doc.leave_approver and not frappe.has_permission(
		DOCTYPE, "submit", doc, user=doc.leave_approver, ignore_share_permissions=True
	):
		frappe.throw(_("The selected approver cannot submit this leave application."), frappe.PermissionError)
	if doc.status != "Approved" or frappe.session.user == "Administrator":
		return
	check_approver_role()
	check_not_own_leave(doc)


def pending_leave(name: str, *, expected_version: str | None = None, lock: bool = False):
	check_approver_role()
	doc = frappe.get_doc(DOCTYPE, name, for_update=lock)
	for operation in ("read", "write", "submit"):
		doc.check_permission(operation)
	check_not_own_leave(doc)
	if expected_version is not None and str(doc.modified) != expected_version:
		frappe.throw(
			_("The leave application changed. Open it again before approving."),
			frappe.TimestampMismatchError,
		)
	if doc.docstatus != DocStatus.draft() or doc.status != "Open":
		frappe.throw(_("Only open draft leave applications can be approved."))
	return doc


def approve(name: str, *, expected_version: str | None = None) -> dict[str, str]:
	doc = pending_leave(name, lock=True, expected_version=expected_version)
	doc.status = "Approved"
	doc.submit()
	return {"name": doc.name}


def cancel(name: str, *, expected_version: str) -> dict[str, str]:
	if HR_ROLE not in frappe.get_roles():
		frappe.throw(_("You do not have permission to cancel leave."), frappe.PermissionError)
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	doc.check_permission("read")
	doc.check_permission("cancel")
	if str(doc.modified) != expected_version:
		frappe.throw(
			_("The leave application changed. Open it again before cancelling."),
			frappe.TimestampMismatchError,
		)
	if not doc.docstatus.is_submitted():
		frappe.throw(_("Only submitted leave applications can be cancelled."), frappe.ValidationError)
	doc.flags.hrms_tr_version_checked = True
	doc.cancel()
	return {"name": doc.name}


def get_approver(employee: str) -> str | None:
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return frappe.get_attr(HRMS_APPROVER_METHOD)(employee)
