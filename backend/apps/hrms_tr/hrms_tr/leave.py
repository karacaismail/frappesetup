"""Use Frappe and HRMS permissions and validation for leave approvals."""

from typing import Annotated

import frappe
from frappe import _
from frappe.model.docstatus import DocStatus
from pydantic import StringConstraints

from hrms_tr.access import DOCTYPE

HR_ROLE = "HRMS TR Admin"
APPROVER_ROLES = ("HRMS TR Manager", HR_ROLE)

LeaveName = Annotated[str, StringConstraints(min_length=1, max_length=140)]


def check_approver_role():
	if not set(APPROVER_ROLES).intersection(frappe.get_roles()):
		frappe.throw(_("You do not have permission to approve leave."), frappe.PermissionError)


def check_not_own_leave(doc):
	if frappe.db.get_value("Employee", doc.employee, "user_id") == frappe.session.user:
		frappe.throw(_("You cannot approve your own leave."), frappe.PermissionError)


def check_hr_role():
	if frappe.session.user != "Administrator" and HR_ROLE not in frappe.get_roles():
		frappe.throw(_("Only HRMS TR Admin can cancel or amend leave applications."), frappe.PermissionError)


def validate_cancellation(doc, method=None):
	check_hr_role()


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


def pending_leave(name: str, *, lock: bool = False, expected_version: str | None = None):
	check_approver_role()
	doc = frappe.get_doc(DOCTYPE, name, for_update=lock)
	for operation in ("read", "write", "submit"):
		doc.check_permission(operation)
	check_not_own_leave(doc)
	if doc.docstatus != DocStatus.draft() or doc.status != "Open":
		frappe.throw(_("Only open draft leave applications can be approved."))
	if expected_version is not None and str(doc.modified) != expected_version:
		frappe.throw(_("The leave application changed. Open it again before approving."))
	return doc


def approve(name: str, *, expected_version: str | None = None) -> dict:
	doc = pending_leave(name, lock=True, expected_version=expected_version)
	doc.status = "Approved"
	doc.submit()
	return {"name": doc.name}
