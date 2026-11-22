"""Authenticate the shared, session-bound agent token on the completion path."""

from hashlib import sha256

import frappe
from frappe.sessions import get_expired_threshold

COMPLETE_PATH = "/api/method/platform_core.api.model.complete"
PREFIX = "fsat_"
CACHE_PREFIX = "yz_agent_token:"
DEFAULT_AUDIENCE = "agent-service"


def authenticate_request():
	"""Limit agent credentials to the model completion route and POST."""
	request = frappe.request
	if request is None or request.path != COMPLETE_PATH or request.method != "POST":
		return
	scheme, _, token = (frappe.get_request_header("Authorization") or "").partition(" ")
	if scheme.lower() != "bearer" or not token.startswith(PREFIX) or len(token) > 128:
		return
	# Frappe gives the cmd parameter precedence over the path.
	if "cmd" in frappe.form_dict or "cmd" in request.args:
		raise frappe.AuthenticationError
	if request.cookies.get("sid") not in (None, "", "Guest"):
		raise frappe.AuthenticationError
	if frappe.session.user not in ("", "Guest"):
		raise frappe.AuthenticationError
	key = CACHE_PREFIX + sha256(token.encode()).hexdigest()
	record = frappe.cache.get_value(key, use_local_cache=False)
	audience = frappe.conf.get("ai_agent_audience") or DEFAULT_AUDIENCE
	if not record or record.get("audience") != audience:
		raise frappe.AuthenticationError
	sessions = frappe.qb.DocType("Sessions")
	if not (
		frappe.qb.from_(sessions)
		.select(sessions.sid)
		.where(sessions.sid == record["sid"])
		.where(sessions.user == record["user"])
		.where(sessions.lastupdate > get_expired_threshold())
		.limit(1)
		.run()
	):
		raise frappe.AuthenticationError
	if not frappe.db.get_value("User", record["user"], "enabled"):
		raise frappe.AuthenticationError
	# Like Frappe API-key auth, keep the validated request body across set_user.
	form = frappe.local.form_dict
	frappe.set_user(record["user"])
	frappe.local.form_dict = form
	frappe.local.model_gateway_agent_calls = frappe.cache.make_key(key + ":calls")


def is_agent():
	return bool(getattr(frappe.local, "model_gateway_agent_calls", None))


def spend_call():
	"""Reserve one call without creating a counter after its TTL has expired."""
	key = frappe.local.model_gateway_agent_calls
	return bool(
		frappe.cache.eval(
			"local n = tonumber(redis.call('GET', KEYS[1])); "
			"if not n or n <= 0 then return 0 end; redis.call('DECR', KEYS[1]); return 1",
			1,
			key,
		)
	)
