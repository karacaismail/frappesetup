"""Use Frappe and HRMS permissions and validation for leave approvals."""

from typing import Annotated

import frappe
from frappe import _
from frappe.model.docstatus import DocStatus
from pydantic import StringConstraints

DOCTYPE = "Leave Application"
APPROVER_ROLES = ("CronHR Manager", "CronHR HR")

LeaveName = Annotated[str, StringConstraints(min_length=1, max_length=140)]


def check_approver_role():
	if not set(APPROVER_ROLES).intersection(frappe.get_roles()):
		frappe.throw(_("You do not have permission to approve leave."), frappe.PermissionError)


def check_not_own_leave(doc):
	if frappe.db.get_value("Employee", doc.employee, "user_id") == frappe.session.user:
		frappe.throw(_("You cannot approve your own leave."), frappe.PermissionError)


def validate_approval(doc, method=None):
	"""Apply the approval role even when a draft is changed through a native Frappe route."""
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
