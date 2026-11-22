"""Serve the tenant shell with a token from the current web session."""

import frappe
from frappe.sessions import get_csrf_token

no_cache = 1
sitemap = 0


def get_context(context):
	frappe.local.response_headers.update(
		{
			"Cache-Control": "private, no-store",
			"Vary": "Cookie",
		}
	)
	if frappe.session.user == "Guest" or frappe.session.sid in (None, "", "Guest"):
		frappe.local.flags.redirect_location = "/login?redirect-to=/panel"
		raise frappe.Redirect(302)

	context.panel_csrf_token = get_csrf_token()
