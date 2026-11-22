"""Link searches on governed document types.

A link field or an app can name its own search function, and Frappe returns whatever that
function returns (`frappe/desk/search.py:133`). Such a function may ignore record rules and
field levels. The engine cannot inspect it, so it filters the result: only records the user may
list are kept, and extra columns are dropped unless the user may read every field.
`hooks.py` puts these functions in place of Frappe's two search endpoints.
"""

import frappe
from frappe import _
from frappe.desk import search

from platform_core.erisim import reports, rules

VERIFIED_QUERIES_HOOK = "access_rule_verified_queries"


def verified_queries() -> set[str]:
	"""Search functions an app vouches for: they apply record rules and field levels themselves."""
	return set(frappe.get_hooks(VERIFIED_QUERIES_HOOK) or [])


def custom_query(doctype: str, query: str | None) -> str | None:
	"""The custom search function Frappe will call for this search, if any."""
	if query:
		return query
	standard = (frappe.get_hooks().standard_queries or {}).get(doctype)
	return standard[-1] if standard else None


def needs_filter(doctype: str, query: str | None) -> bool:
	used = custom_query(doctype, query)
	if not used or used in verified_queries() or frappe.session.user == "Administrator":
		return False
	user = frappe.session.user
	return not (reports.sees_every_record(doctype, user) and reports.reads_fields(doctype, ["*"], user))


def _name_of(row):
	if isinstance(row, dict):
		return row.get("value") or row.get("name")
	return row[0] if row else None


def allowed_names(doctype: str, rows: list) -> set[str]:
	names = [name for name in map(_name_of, rows) if name]
	if not names:
		return set()
	return set(
		frappe.get_list(doctype, filters={"name": ("in", names)}, pluck="name", limit_page_length=len(names))
	)


@frappe.whitelist(methods=["GET", "POST"])
def search_link(
	doctype: str,
	txt: str,
	query: str | None = None,
	filters: str | dict | list | None = None,
	page_length: int = 10,
	searchfield: str | None = None,
	reference_doctype: str | None = None,
	ignore_user_permissions: bool = False,
	link_fieldname: str | None = None,
) -> list:
	"""`frappe.desk.search.search_link` with the result limited to what the user may list."""
	if not frappe.has_permission(doctype, "select"):
		frappe.throw(_("No permission to search {0}.").format(doctype), frappe.PermissionError)
	results = search.search_link(
		doctype,
		txt,
		query,
		filters=filters,
		page_length=page_length,
		searchfield=searchfield,
		reference_doctype=reference_doctype,
		ignore_user_permissions=ignore_user_permissions,
		link_fieldname=link_fieldname,
	)
	if not results or not needs_filter(doctype, query):
		return results
	allowed = allowed_names(doctype, results)
	return [{"value": row["value"], "description": ""} for row in results if row.get("value") in allowed]


@frappe.whitelist(methods=["GET", "POST"])
def search_widget(
	doctype: str,
	txt: str,
	query: str | None = None,
	searchfield: str | None = None,
	start: int = 0,
	page_length: int = 10,
	filters: str | None | dict | list = None,
	filter_fields: str | None = None,
	as_dict: bool = False,
	reference_doctype: str | None = None,
	ignore_user_permissions: bool = False,
	link_fieldname: str | None = None,
) -> list:
	"""`frappe.desk.search.search_widget` with the result limited to what the user may list."""
	if not frappe.has_permission(doctype, "select"):
		frappe.throw(_("No permission to search {0}.").format(doctype), frappe.PermissionError)
	results = search.search_widget(
		doctype,
		txt,
		query,
		searchfield=searchfield,
		start=start,
		page_length=page_length,
		filters=filters,
		filter_fields=filter_fields,
		as_dict=as_dict,
		reference_doctype=reference_doctype,
		ignore_user_permissions=ignore_user_permissions,
		link_fieldname=link_fieldname,
	)
	if not results or not needs_filter(doctype, query):
		return results
	allowed = allowed_names(doctype, results)
	names = [name for name in map(_name_of, results) if name in allowed]
	return [{"name": name} for name in names] if as_dict else [[name] for name in names]
