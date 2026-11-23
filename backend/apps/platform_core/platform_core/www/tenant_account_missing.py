"""Error page of `keycloak_callback` for a Keycloak account that has no user on this tenant site.

The page is reached only through `frappe.respond_as_web_page(template="tenant_account_missing")`.
That call sets `frappe.local.message` before the page renders (frappe/__init__.py:1281, Frappe 16.56.0).
A direct request of `/tenant_account_missing` has no such message. The page then raises
`PageDoesNotExistError`, and `frappe.website.serve.handle_exception` answers with the 404 page
(review item K-1: no standalone address for the error page).
"""

import frappe

no_cache = 1
sitemap = 0


def get_context(context):
	if not hasattr(frappe.local, "message"):
		raise frappe.PageDoesNotExistError
	# The page follows the request language like the sign-in page (GILT step 2b).
	context.lang = frappe.local.lang or "en"
	return context
