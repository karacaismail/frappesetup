"""External OAuth authentication confined to the site's MCP resource."""

import hashlib

import frappe
from frappe import _
from redis.exceptions import RedisError
from werkzeug.wrappers import Response

from platform_core.ai import access, agent_token, store
from platform_core.ai.errors import CONTEXT
from platform_core.identity import api as identity_api

METADATA_PATH = "/api/method/platform_core.api.ai.mcp_resource_metadata"
SCOPE = "mcp"


def add_challenge(config: dict) -> None:
	origin = config["resource"].removesuffix(agent_token.MCP_PATH)
	frappe.local.response_headers["WWW-Authenticate"] = (
		f'Bearer resource_metadata="{origin}{METADATA_PATH}", scope="{SCOPE}"'
	)


def resource_metadata() -> Response:
	config = identity_api.mcp_oauth_config()
	request = frappe.request
	if not config or request.path != METADATA_PATH or "cmd" in request.args:
		return Response(status=404)
	return Response(
		frappe.as_json(
			{
				"resource": config["resource"],
				"authorization_servers": [config["issuer"]],
				"scopes_supported": [SCOPE],
				"bearer_methods_supported": ["header"],
			}
		),
		mimetype="application/json",
	)


def authenticate_request() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None or request.method != "POST" or request.path != agent_token.MCP_PATH:
		return
	config = identity_api.mcp_oauth_config()
	if not config:
		return

	scheme, _separator, token = (frappe.get_request_header("Authorization") or "").partition(" ")
	if scheme.lower() != "bearer" or token.startswith(agent_token.PREFIX):
		return

	if any(key in request.args or key in frappe.form_dict for key in ("cmd", "access_token")):
		add_challenge(config)
		raise frappe.AuthenticationError(_("MCP token rejected.", context="platform_core.identity"))
	if frappe.session.user not in ("", "Guest") or request.cookies.get("sid") not in (None, "", "Guest"):
		raise frappe.PermissionError(_("Send either a session cookie or a bearer token.", context=CONTEXT))

	try:
		identity = identity_api.verify_mcp_token(token)
	except identity_api.ServiceTokenRejected as error:
		add_challenge(config)
		if getattr(error, "reason", None) == "expired":
			frappe.logger("mcp_oauth", allow_site=True).warning("token_expired")
		raise

	form_dict = frappe.local.form_dict
	frappe.set_user(identity["account"])
	frappe.local.form_dict = form_dict
	frappe.local.mcp_oauth = {
		"budget": hashlib.sha256(f"{identity['client_id']}\0{token}".encode()).hexdigest(),
		"expires_at": identity["expires_at"],
	}


class CallBudgetUnavailable(frappe.ValidationError):
	http_status_code = 503
	skip_error_log = True


def spend_call(identity: dict) -> str | None:
	"""Charge before dispatch. A failed tool or denied proposal cannot refund the call."""
	access.require_clean_transaction()
	# End the identity read snapshot before MariaDB locks the latest shared row.
	frappe.db.rollback()
	try:
		reason = store.charge_mcp_call(identity["budget"], identity["expires_at"], agent_token.MAX_CALLS)
	except RedisError:
		frappe.db.rollback()
		raise CallBudgetUnavailable(_("MCP call allowance unavailable.", context=CONTEXT)) from None
	if reason is None:
		access.commit_own_writes()
	return reason
