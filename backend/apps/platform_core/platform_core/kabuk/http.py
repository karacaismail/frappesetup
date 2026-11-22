"""Shared authentication and conditional response handling."""

import frappe

from platform_core.kabuk.serialization import etag_for, matches_etag


def require_session() -> str:
	frappe.local.response_headers.update(
		{
			"Cache-Control": "private, no-store",
			"Vary": "Cookie, Authorization",
		}
	)
	user = frappe.session.user
	if user == "Guest" or not frappe.session.sid or frappe.session.sid == "Guest":
		frappe.throw(frappe._("Log in to access this resource."), frappe.PermissionError)
	return user


def conditional_response(payload: dict, user: str, version: str) -> dict | None:
	"""Call only after evaluating the current user's authorization."""
	etag = etag_for(frappe.local.site, user, version, payload)
	frappe.local.response_headers.update(
		{
			"ETag": etag,
			"Cache-Control": "private, no-cache, must-revalidate",
			"Vary": "Cookie, Authorization",
		}
	)
	if matches_etag(frappe.get_request_header("If-None-Match"), etag):
		frappe.response["http_status_code"] = 304
		return None
	return payload
