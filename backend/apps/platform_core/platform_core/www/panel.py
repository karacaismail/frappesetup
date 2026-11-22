"""Serve the tenant shell with a token from the current web session."""

import frappe
from frappe.sessions import get_csrf_token

from platform_core.shell.headers import STRICT_CSP
from platform_core.shell.http import has_session_cookie

no_cache = 1
sitemap = 0


def get_context(context):
	frappe.local.response_headers.update(
		{
			"Cache-Control": "private, no-store",
			"Vary": "Cookie",
			"Content-Security-Policy": STRICT_CSP,
			"X-Frame-Options": "DENY",
			"X-Content-Type-Options": "nosniff",
		}
	)
	if not has_session_cookie():
		frappe.local.flags.redirect_location = "/login?redirect-to=/panel"
		raise frappe.Redirect(302)

	context.panel_language = frappe.local.lang or "en"
	context.panel_csrf_token = get_csrf_token()
