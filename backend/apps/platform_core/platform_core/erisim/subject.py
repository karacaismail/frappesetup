"""Özne: isteği yapan kullanıcının çalışan kaydı, bölümü ve şirketi.

Değerler yalnız istek boyunca saklanır. Böylece `reports_to` değişikliği sonraki istekte etki eder.
Karar notu 7. bölüm.
"""

import frappe
from frappe.utils.caching import request_cache

EMPLOYEE = "Employee"
DEPARTMENT = "Department"


def has_doctype(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype, cache=True))


@request_cache
def subject(user: str) -> dict:
	"""Öznenin değerleri. Etkin çalışan kaydı yoksa çalışana bağlı değerler `None` olur."""
	values = {"user": user, "employee": None, "lft": None, "rgt": None, "department": None, "company": None}
	if not has_doctype(EMPLOYEE):
		return values
	# Motorun kendi okuması. İzin süzmesi burada kancayı yeniden çağırırdı (G-3 istisnası).
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
	"""Bölümün ağaçtaki aralığı. Alt bölümler bu aralığın içindedir."""
	if not department or not has_doctype(DEPARTMENT):
		return None
	row = frappe.db.get_value(DEPARTMENT, department, ["lft", "rgt"], as_dict=True)
	return (row.lft, row.rgt) if row else None


def variable(name: str, values: dict):
	"""`$user...` değişkeninin değeri."""
	return values[{"$user": "user"}.get(name) or name.removeprefix("$user.")]
