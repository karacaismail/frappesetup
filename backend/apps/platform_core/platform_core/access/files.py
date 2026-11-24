"""The file list on governed document types (G-121).

A private file is read through the record it is attached to. Frappe's `File` hook asks the
record (`frappe/core/doctype/file/file.py:1108`), so the single file and its download already
follow the rule. Frappe's list condition for `File` looks only at the document type of the
record (`file.py:1128`). A user who may read the type would see every attachment of it in the
file list: the file name and the name of the record it belongs to.

The engine adds one condition to the file list. A file attached to a governed document type is
listed only if its record passes the list rule of the user. Other files are left to Frappe.
"""

import frappe
from pypika.terms import Criterion

from platform_core.access import engine, rules

FILE = "File"


def list_criterion(user: str) -> Criterion | None:
	"""The condition for the file list. Returns `None` if no document type is governed."""
	governed = sorted(rules.active_rules())
	if not governed:
		return None
	file = frappe.qb.DocType(FILE)
	conditions = []
	for doctype in governed:
		table = frappe.qb.DocType(doctype)
		visible = frappe.qb.from_(table).select(table.name).where(engine.list_criterion(doctype, user))
		conditions.append(
			file.attached_to_doctype.isnull()
			| (file.attached_to_doctype != doctype)
			| file.attached_to_name.isin(visible)
		)
	return Criterion.all(conditions)
