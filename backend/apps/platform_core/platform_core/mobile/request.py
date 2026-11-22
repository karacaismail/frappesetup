"""Mobile HTTP boundary. Identity verification belongs to the identity hook."""

import json
import re
import time
from dataclasses import dataclass

import frappe

from .protocol import BODY_BYTES, REQUESTS_PER_MINUTE, MobileError, content_digest

APP_VERSION = re.compile(r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}")
CONTRACT_VERSION = re.compile(r"[1-9][0-9]{0,2}")


@dataclass(frozen=True)
class Identity:
	site: str
	account: str
	principal: str
	scope: str


def _unique_keys(pairs):
	result = {}
	for name, value in pairs:
		if name in result:
			raise ValueError("duplicate JSON key")
		result[name] = value
	return result


def _read_json(request):
	if request.content_length is not None and request.content_length > BODY_BYTES:
		raise MobileError("body_too_large", 413)
	if not request.is_json:
		raise MobileError("json_required", 415)
	raw = request.get_data(cache=True)
	if len(raw) > BODY_BYTES:
		raise MobileError("body_too_large", 413)
	try:
		body = json.loads(raw, object_pairs_hook=_unique_keys)
	except (ValueError, RecursionError) as error:
		raise MobileError("invalid_json") from error
	if not isinstance(body, dict):
		raise MobileError("invalid_json")
	return body


def _limit_and_count(principal, app_version, contract_version):
	now = int(time.time())
	minute = now // 60
	rate_key = frappe.cache.make_key(f"mobile-rate:{principal}:{minute}")
	with frappe.cache.pipeline() as pipe:
		pipe.incr(rate_key)
		pipe.expire(rate_key, 120)
		count, _ = pipe.execute()
	if count > REQUESTS_PER_MINUTE:
		frappe.local.response_headers["Retry-After"] = str(60 - now % 60)
		raise MobileError("rate_limit", 429)

	day = now // 86400
	metrics_key = frappe.cache.make_key(f"mobile-versions:{day}")
	with frappe.cache.pipeline() as pipe:
		pipe.hincrby(metrics_key, f"{contract_version}:{app_version}", 1)
		pipe.expire(metrics_key, 7 * 86400)
		pipe.execute()


def mobile_request(endpoint):
	request = frappe.local.request
	expected_path = f"/api/method/platform_core.api.mobile.{endpoint}"
	if request.path != expected_path or "cmd" in request.args:
		raise MobileError("invalid_mobile_route")
	authorization = request.headers.get("Authorization", "").split()
	if len(authorization) != 2 or authorization[0].lower() != "bearer":
		raise MobileError("mobile_token_required", 401)

	# Set only by the identity hook after it verifies the token, site, client,
	# scopes and absence of a live Frappe cookie session.
	identity = getattr(frappe.local, "mobile_identity", None)
	if not isinstance(identity, dict) or identity.get("site") != frappe.local.site:
		raise MobileError("mobile_token_required", 401)
	account = identity.get("account")
	scope = identity.get("scope")
	if account != frappe.session.user or not account or account == "Guest" or scope != "mobile":
		raise MobileError("mobile_token_required", 401)

	issuer = identity.get("issuer")
	subject = identity.get("subject")
	if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
		raise MobileError("mobile_token_required", 401)
	principal = content_digest([issuer, subject])

	app_version = request.headers.get("X-Mobile-App-Version", "")
	contract_version = request.headers.get("X-Mobile-Contract-Version", "")
	if not APP_VERSION.fullmatch(app_version) or not CONTRACT_VERSION.fullmatch(contract_version):
		raise MobileError("invalid_client_version")
	_limit_and_count(principal, app_version, contract_version)
	if contract_version != "1":
		raise MobileError("unsupported_contract_version")
	body = _read_json(request)
	if "cmd" in body:
		raise MobileError("invalid_mobile_route")
	return Identity(frappe.local.site, account, principal, scope), body


def _error_response(error):
	frappe.db.rollback()
	frappe.local.response["http_status_code"] = error.status
	frappe.local.response["code"] = error.code
	if error.current is not None:
		frappe.local.response["current"] = error.current
	return None


def endpoint_response(endpoint, action):
	try:
		identity, body = mobile_request(endpoint)
	except MobileError as error:
		return _error_response(error)

	# MariaDB can reject a locking read when auth opened an older snapshot.
	# Roll back the entire attempt before rerunning database-only commands.
	for _ in range(3):
		try:
			return action(identity, body)
		except MobileError as error:
			return _error_response(error)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()

	frappe.local.response_headers["Retry-After"] = "1"
	return _error_response(MobileError("mobile_busy", 503))
