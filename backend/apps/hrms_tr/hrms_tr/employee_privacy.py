"""Personal data of an employee record (AJA-1024).

The personal fields of an employee sit on their own permission level (`setup.py`).
A file attached to an employee can hold the same data, for example a passport scan.
Only a user who reads that level opens such a file.
"""

import frappe
from frappe.permissions import get_valid_perms

from hrms_tr.setup import EMPLOYEE_PERSONAL_LEVEL

EMPLOYEE = "Employee"


def reads_personal_fields(user: str) -> bool:
	"""One of the user's roles reads the personal level of the employee record."""
	if user == "Administrator":
		return True
	return any(
		perm.permlevel == EMPLOYEE_PERSONAL_LEVEL and perm.read for perm in get_valid_perms(EMPLOYEE, user)
	)


def attachment_allowed(file, user: str | None = None) -> bool:
	"""A file attached to an employee needs the personal level. Every other file is left alone."""
	if getattr(file, "attached_to_doctype", None) != EMPLOYEE:
		return True
	return reads_personal_fields(user or frappe.session.user)


def file_has_permission(doc, ptype=None, user=None, debug=False) -> bool:
	"""The record hook of File. Frappe's hooks only narrow: `True` grants nothing."""
	return attachment_allowed(doc, user)
