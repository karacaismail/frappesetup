"""Serve the tenant shell with a token from the current web session."""

import secrets
from urllib.parse import quote

import frappe
from frappe.sessions import get_csrf_token

from platform_core.shell.headers import STRICT_CSP, panel_csp
from platform_core.shell.http import has_session_cookie
from platform_core.shell.panel_assets import current_panel_assets

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
		# Client routes (/panel/<path>) come back to the same route after login.
		path = quote("/" + (getattr(frappe.local, "path", None) or "panel").strip("/"), safe="/")
		frappe.local.flags.redirect_location = f"/login?redirect-to={path}"
		raise frappe.Redirect(302)

	context.panel_language = frappe.local.lang or "en"
	context.panel_csrf_token = get_csrf_token()
	context.panel_assets = current_panel_assets()
	if context.panel_assets:
		context.panel_csp_nonce = secrets.token_urlsafe(18)
		frappe.local.response_headers["Content-Security-Policy"] = panel_csp(context.panel_csp_nonce)
