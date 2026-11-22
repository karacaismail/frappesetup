"""Set response header defaults for tenant sites running Platform Core."""

import frappe
from werkzeug.wrappers import Request, Response

CSP_RESTRICTIONS = "object-src 'none'; base-uri 'self'; form-action 'self'"
BASE_CSP = f"frame-ancestors 'self'; {CSP_RESTRICTIONS}"
UNFRAMED_CSP = f"frame-ancestors 'none'; {CSP_RESTRICTIONS}"
PANEL_CSP = f"default-src 'self'; script-src 'self'; {UNFRAMED_CSP}"
SECURITY_HEADERS = {
	"X-Content-Type-Options": "nosniff",
	"Referrer-Policy": "strict-origin-when-cross-origin",
	"X-Frame-Options": "SAMEORIGIN",
}


def add_security_headers(response: Response | None, request: Request | None = None) -> None:
	if response is None:
		return

	# Frappe applies pending endpoint headers after the after_request hooks.
	pending = frappe.local.response_headers
	# The native login template contains inline JavaScript. Tighten framing only.
	policy = UNFRAMED_CSP if request is not None and request.path.rstrip("/") == "/login" else BASE_CSP
	headers = {**SECURITY_HEADERS, "Content-Security-Policy": policy}
	for name, header_value in headers.items():
		if name not in pending:
			response.headers.setdefault(name, header_value)
