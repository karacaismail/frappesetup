"""Subject: the employee record, department and company of the user who makes the request.

The values are kept only during the request. So a `reports_to` change takes effect in the next request.
Decision note, section 7.
"""

import frappe
from frappe.utils.caching import request_cache

EMPLOYEE = "Employee"
DEPARTMENT = "Department"


def has_doctype(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype, cache=True))


@request_cache
def subject(user: str) -> dict:
	"""The values of the subject. If there is no active employee record, the values that depend on the employee are `None`."""
	values = {"user": user, "employee": None, "lft": None, "rgt": None, "department": None, "company": None}
	if not has_doctype(EMPLOYEE):
		return values
	# The own read of the engine. Permission filtering would call the hook again here (exception to G-3).
	row = frappe.db.get_value(
		EMPLOYEE,
		{"user_id": user, "status": "Active"},
		["name", "lft", "rgt", "department", "company"],
		as_dict=True,
	)
	if row:
		values.update(
			employee=row.name, lft=row.lft, rgt=row.rgt, department=row.department, company=row.company
		)
	return values


@request_cache
def department_range(department: str | None) -> tuple[int, int] | None:
	"""The range of the department in the tree. The child departments are inside this range."""
	if not department or not has_doctype(DEPARTMENT):
		return None
	row = frappe.db.get_value(DEPARTMENT, department, ["lft", "rgt"], as_dict=True)
	return (row.lft, row.rgt) if row else None


def variable(name: str, values: dict):
	"""The value of the `$user...` variable."""
	return values[{"$user": "user"}.get(name) or name.removeprefix("$user.")]
