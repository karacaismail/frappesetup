"""Link searches on governed document types.

A link field or an app can name its own search function, and Frappe returns whatever that
function returns (`frappe/desk/search.py:133`). Such a function may ignore record rules and
field levels, and it may pick records by a field the user cannot read.

Rule (decision D of the third review): on a governed document type only Frappe's standard
search and the search functions on the engine's allow-list run. An allow-listed function must
itself read through permission-aware calls; its module is checked on every search. Every other
custom search function is refused, for every user.

`hooks.py` puts `search_link` and `search_widget` in place of Frappe's two search endpoints.
Python code must use `platform_core.erisim.api`: Frappe's own functions cannot be intercepted
from Python without changing Frappe.
"""

import inspect

import frappe
from frappe import _
from frappe.desk import search

from platform_core.erisim import code_check, rules

ALLOWED_QUERIES_HOOK = "access_rule_allowed_queries"


def allowed_queries() -> set[str]:
	"""Search functions apps put on the allow-list in `hooks.py`."""
	return set(frappe.get_hooks(ALLOWED_QUERIES_HOOK) or [])


def custom_query(doctype: str, query: str | None) -> str | None:
	"""The custom search function Frappe will call for this search, if any."""
	if query:
		return query
	standard = (frappe.get_hooks().standard_queries or {}).get(doctype)
	return standard[-1] if standard else None


def query_source(query: str) -> str | None:
	try:
		return inspect.getsource(inspect.getmodule(frappe.get_attr(query)))
	except (ImportError, AttributeError, OSError, TypeError):
		return None


def guard(doctype: str, query: str | None = None) -> None:
	"""Refuse a custom search on a governed document type unless it is allow-listed and checked."""
	used = custom_query(doctype, query)
	if not used or frappe.session.user == "Administrator" or not rules.is_governed(doctype):
		return
	if used not in allowed_queries():
		frappe.throw(
			_("Search function {0} is not allowed on {1}, which is governed by Access Rules.").format(
				frappe.bold(used), frappe.bold(doctype)
			),
			frappe.PermissionError,
		)
	found = code_check.problems(query_source(used), None)
	if found:
		frappe.throw(
			_("Search function {0} does not read through permission-aware calls only: {1}").format(
				frappe.bold(used), ", ".join(found)
			),
			frappe.PermissionError,
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
	"""`frappe.desk.search.search_link` behind the link search rule."""
	if not frappe.has_permission(doctype, "select"):
		frappe.throw(_("No permission to search {0}.").format(doctype), frappe.PermissionError)
	guard(doctype, query)
	return search.search_link(
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
	"""`frappe.desk.search.search_widget` behind the link search rule."""
	if not frappe.has_permission(doctype, "select"):
		frappe.throw(_("No permission to search {0}.").format(doctype), frappe.PermissionError)
	guard(doctype, query)
	return search.search_widget(
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
