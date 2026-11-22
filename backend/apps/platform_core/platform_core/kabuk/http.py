"""Shared authentication and conditional response handling."""

from urllib.parse import unquote

import frappe

from platform_core.kabuk.serialization import etag_for, matches_etag


def has_session_cookie() -> bool:
	sid = frappe.session.sid
	cookie = unquote(frappe.request.cookies.get("sid", ""))
	session = frappe.local.session_obj
	return bool(
		sid
		and sid != "Guest"
		and frappe.session.user != "Guest"
		and sid == cookie == session.sid
		and frappe.session.user == session.user
	)


def require_session() -> str:
	frappe.local.response_headers.update(
		{
			"Cache-Control": "private, no-store",
			"Vary": "Cookie, Authorization",
		}
	)
	user = frappe.session.user
	if not has_session_cookie():
		frappe.throw(
			frappe._("Log in to access this resource.", context="shell.session"), frappe.PermissionError
		)
	return user


def conditional_response(payload: dict, user: str, version: str) -> dict | None:
	"""Call only after evaluating the current user's authorization."""
	etag = etag_for(frappe.local.site, user, version, payload)
	frappe.local.response_headers.update(
		{
			"ETag": etag,
			"Cache-Control": "private, no-store",
			"Vary": "Cookie, Authorization",
		}
	)
	if matches_etag(frappe.get_request_header("If-None-Match"), etag):
		frappe.response["http_status_code"] = 304
		return None
	return payload
