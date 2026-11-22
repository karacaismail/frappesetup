"""Link searches on governed document types.

A link field or an app can name its own search function, and Frappe returns whatever that
function returns (`frappe/desk/search.py:133`). Such a function may ignore record rules and
field levels, and it may pick records by a field the user cannot read.

Rule: on a governed document type only Frappe's standard search runs. Every custom search
function is refused, for every user, the Administrator user included. There is no allow-list. An allow-list with a static code
check was tried and removed: the check could be bypassed and can never be complete.

`hooks.py` puts `search_link` and `search_widget` in place of Frappe's two search endpoints.
Python code must use `platform_core.erisim.api`: Frappe's own functions cannot be intercepted
from Python without changing Frappe.
"""

import frappe
from frappe import _
from frappe.desk import search

from platform_core.erisim import rules


def custom_query(doctype: str, query: str | None) -> str | None:
	"""The custom search function Frappe will call for this search, if any."""
	if query:
		return query
	standard = (frappe.get_hooks().standard_queries or {}).get(doctype)
	return standard[-1] if standard else None


def guard(doctype: str, query: str | None = None) -> None:
	"""Refuse every custom search function on a governed document type.

	There is no exception, not for a System Manager and not for the Administrator user: Frappe's
	own search would run the function for them as for anyone else.
	"""
	used = custom_query(doctype, query)
	if not used or not rules.is_governed(doctype):
		return
	frappe.throw(
		_("Search function {0} is not allowed on {1}, which is governed by Access Rules.").format(
			frappe.bold(used), frappe.bold(doctype)
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
