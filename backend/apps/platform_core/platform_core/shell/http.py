"""Shared authentication and conditional response handling."""

from collections.abc import Callable
from urllib.parse import unquote

import frappe
from frappe.api import ApiVersion, get_api_version
from frappe.utils import orjson_dumps
from frappe.utils.response import json_handler, make_logs

from platform_core.shell.serialization import etag_for, matches_etag

MAX_RESPONSE_BYTES = 262_144


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


def no_store() -> None:
	"""The reply is never stored by the browser or by a cache on the way."""
	frappe.local.response_headers.update(
		{
			"Cache-Control": "private, no-store",
			"Vary": "Cookie, Authorization",
		}
	)


def require_session() -> str:
	no_store()
	user = frappe.session.user
	if not has_session_cookie():
		frappe.throw(
			frappe._("Log in to access this resource.", context="shell.session"), frappe.PermissionError
		)
	return user


def conditional_response(payload: dict, user: str, compact: Callable[[dict], dict]) -> dict | None:
	"""Call only after evaluating the current user's authorization."""
	# Measure the same envelope and serializer Frappe uses, including JSON escaping.
	make_logs()
	response = {
		key: value
		for key, value in frappe.local.response.items()
		if key != "http_status_code" and (key != "docs" or value)
	}
	key = "data" if get_api_version() == ApiVersion.V2 and not frappe.form_dict.get("cmd") else "message"
	response[key] = payload
	if len(orjson_dumps(response, default=json_handler, decode=False)) > MAX_RESPONSE_BYTES:
		payload = compact(payload)
		# The compact representation has only bounded scalars and empty collections.
		# Omit transient response diagnostics too, so Frappe cannot exceed the budget.
		frappe.local.response.clear()
		frappe.local.message_log.clear()
		frappe.local.error_log.clear()
		frappe.local.debug_log.clear()
		frappe.flags.error_message = None
	etag = etag_for(frappe.local.site, user, payload["perm_version"], payload)
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
