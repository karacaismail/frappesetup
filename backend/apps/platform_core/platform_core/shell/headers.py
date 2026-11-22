"""Set response header defaults for tenant sites running Platform Core."""

import frappe
from werkzeug.wrappers import Response

SECURITY_HEADERS = {
	"X-Content-Type-Options": "nosniff",
	"Referrer-Policy": "strict-origin-when-cross-origin",
	"X-Frame-Options": "SAMEORIGIN",
}


def add_security_headers(response: Response | None) -> None:
	if response is None:
		return

	# Frappe applies pending endpoint headers after the after_request hooks.
	pending = frappe.local.response_headers
	for name, value in SECURITY_HEADERS.items():
		if name not in pending:
			response.headers.setdefault(name, value)
