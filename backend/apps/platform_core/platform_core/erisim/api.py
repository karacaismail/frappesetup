"""Public functions of the access rule engine.

Other modules of `platform_core` may import this module and nothing else from the engine
(`backend/dev/modul-sinirlari.json`). The AI layer calls `report_guard` before it runs a report.
"""

from platform_core.erisim import link_search, reports


def report_guard(report_name: str, user: str | None = None) -> None:
	"""Raise `frappe.PermissionError` when the report may not run for the user.

	`user` defaults to the session user. The same check runs again inside the Report document
	when the report executes, so calling this is an early answer, not the only protection.
	"""
	reports.guard(report_name, user)


def link_search_guard(doctype: str, query: str | None = None) -> None:
	"""Raise `frappe.PermissionError` when a custom search function may not run on the type."""
	link_search.guard(doctype, query)


def search_link(doctype: str, txt: str, query: str | None = None, **kwargs) -> list:
	"""Link search for Python callers. It follows the same rule as the HTTP endpoint."""
	return link_search.search_link(doctype, txt, query, **kwargs)
