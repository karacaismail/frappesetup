"""G-62 and G-98: the “Tenant Admin” reads the Permission Log of its own site.

Frappe writes a Permission Log row when a role, a role profile, a user's roles or a permission row
changes (`frappe.core.doctype.permission_log`). The type itself stays readable only by a
System Manager. This endpoint gives a page of rows to the two roles of `tenant_admin.require_manager`.
"""

import frappe
from frappe import _

from platform_core.access import tenant_admin

MAX_PAGE_LENGTH = 100
DEFAULT_PAGE_LENGTH = 20
LOG_FIELDS = (
	"name",
	"creation",
	"changed_by",
	"for_doctype",
	"for_document",
	"reference_type",
	"reference",
	"status",
	"changes",
)


class InvalidInput(frappe.ValidationError):
	http_status_code = 400


def _whole(value: object, name: str, low: int, high: int | None) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		number = None
	if number is None or isinstance(value, bool) or number < low or (high is not None and number > high):
		frappe.throw(_("{0} must be a whole number in range.").format(name), InvalidInput)
	return number


def list_permission_logs(
	for_doctype: object = None, for_document: object = None, start: object = 0, page_length: object = None
) -> dict:
	"""A page of Permission Log rows, the newest first."""
	tenant_admin.require_manager()
	start = _whole(start, "start", 0, None)
	page_length = _whole(
		DEFAULT_PAGE_LENGTH if page_length in (None, "") else page_length, "page_length", 1, MAX_PAGE_LENGTH
	)
	filters = {}
	for field, value in (("for_doctype", for_doctype), ("for_document", for_document)):
		if value in (None, ""):
			continue
		if not isinstance(value, str) or len(value) > 140:
			frappe.throw(_("{0} must be a name.").format(field), InvalidInput)
		filters[field] = value
	# The caller's right was checked by `require_manager` (exception to G-3).
	rows = frappe.get_all(
		"Permission Log",
		filters=filters,
		fields=list(LOG_FIELDS),
		order_by="creation desc, name desc",
		limit_start=start,
		limit_page_length=page_length + 1,
	)
	logs = []
	for row in rows[:page_length]:
		try:
			changes = frappe.parse_json(row.changes) if row.changes else {}
		except ValueError:
			changes = {}
		logs.append(
			{
				"name": row.name,
				"changed_at": str(row.creation),
				"changed_by": row.changed_by,
				"for_doctype": row.for_doctype,
				"for_document": row.for_document,
				"reference_type": row.reference_type,
				"reference": row.reference,
				"status": row.status,
				"changes": changes if isinstance(changes, dict) else {},
			}
		)
	return {"logs": logs, "start": start, "page_length": page_length, "has_more": len(rows) > page_length}
