"""A search function used by the link search tests. This module holds no tests.

The function is not an endpoint: it carries no whitelist decorator, so nothing in the shipped
package can call it over HTTP. The tests register it with Frappe only while they run.
The engine checks the source of this whole module, so only permission-aware code may live here.
"""

import frappe


@frappe.validate_and_sanitize_search_inputs
def scoped_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""A careful custom search: it reads through `frappe.get_list`."""
	if not frappe.has_permission(doctype, "select"):
		frappe.throw("Not permitted", frappe.PermissionError)
	return frappe.get_list(doctype, fields=["name", "title"], as_list=True, limit=500)
