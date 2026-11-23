"""Set response header defaults for tenant sites running Platform Core."""

import frappe
from werkzeug.wrappers import Request, Response

CSP_RESTRICTIONS = "object-src 'none'; base-uri 'self'; form-action 'self'"
BASE_CSP = f"frame-ancestors 'self'; {CSP_RESTRICTIONS}"
STRICT_CSP = f"default-src 'self'; script-src 'self'; frame-ancestors 'none'; {CSP_RESTRICTIONS}"
SECURITY_HEADERS = {
	"X-Content-Type-Options": "nosniff",
	"Referrer-Policy": "strict-origin-when-cross-origin",
	"X-Frame-Options": "SAMEORIGIN",
}


def panel_csp(nonce: str) -> str:
	"""The /panel policy with the web bundle: the UI library creates nonce-marked style elements."""
	return (
		f"default-src 'self'; script-src 'self'; style-src 'self' 'nonce-{nonce}'; "
		f"frame-ancestors 'none'; {CSP_RESTRICTIONS}"
	)


def add_security_headers(response: Response | None, request: Request | None = None) -> None:
	if response is None:
		return

	# Frappe applies pending endpoint headers after the after_request hooks.
	pending = frappe.local.response_headers
	# Frappe can resolve the site home page to the tenant login template.
	request_path = request.path.strip("/ ").removesuffix(".html") if request is not None else ""
	is_login = getattr(frappe.local, "path", None) == "login" or request_path == "login"
	headers = {
		**SECURITY_HEADERS,
		"Content-Security-Policy": STRICT_CSP if is_login else BASE_CSP,
	}
	if is_login:
		headers["X-Frame-Options"] = "DENY"
	for name, header_value in headers.items():
		if name not in pending:
			response.headers.setdefault(name, header_value)
