"""Mobile HTTP boundary. Identity verification belongs to the identity hook."""

import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone

from .protocol import BODY_BYTES, REQUESTS_PER_MINUTE, TOKEN_CLOCK_SKEW_SECONDS, MobileError, content_digest
from .sessions import is_session_revoked, valid_session_id

APP_VERSION = re.compile(r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}")
CONTRACT_VERSION = re.compile(r"[1-9][0-9]{0,2}")
MAX_VERSION_BUCKETS = 256
VERSION_COUNTER = """
local bucket = ARGV[1]
if redis.call('HEXISTS', KEYS[1], bucket) == 0
    and redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[2]) then
    bucket = 'other'
end
redis.call('HINCRBY', KEYS[1], bucket, 1)
redis.call('EXPIRE', KEYS[1], ARGV[3])
"""


@dataclass(frozen=True)
class Identity:
	site: str
	account: str
	principal: str
	scope: str
	issued_at: int
	sid: str | None


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
	frappe.cache.eval(
		VERSION_COUNTER, 1, metrics_key, f"{contract_version}:{app_version}", MAX_VERSION_BUCKETS, 7 * 86400
	)


def mobile_request(endpoint):
	request = frappe.local.request
	expected_path = f"/api/method/platform_core.api.mobile.{endpoint}"
	if request.path != expected_path or "cmd" in request.args:
		raise MobileError("invalid_mobile_route")
	authorization = request.headers.get("Authorization", "").split()
	if len(authorization) != 2 or authorization[0].lower() != "bearer":
		raise MobileError("mobile_token_required", 401)

	login_manager = getattr(frappe.local, "login_manager", None)
	if request.cookies.get("sid") not in (None, "", "Guest") and getattr(
		login_manager, "user", "Guest"
	) not in (None, "Guest"):
		raise MobileError("mixed_authentication")

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
	issued_at = identity.get("iat")
	if type(issued_at) is not int or not 0 < issued_at <= int(time.time()) + TOKEN_CLOCK_SKEW_SECONDS:
		raise MobileError("mobile_token_required", 401)
	sid = identity.get("sid")
	if not valid_session_id(sid):
		raise MobileError("mobile_token_required", 401)
	if is_session_revoked(sid):
		raise MobileError("mobile_session_revoked", 401)
	principal = content_digest([issuer, subject])

	return _sync_payload(request, Identity(frappe.local.site, account, principal, scope, issued_at, sid))


def pwa_request(endpoint):
	request = frappe.local.request
	if request.path != f"/api/method/platform_core.api.mobile_pwa.{endpoint}" or "cmd" in request.args:
		raise MobileError("invalid_mobile_route")
	if "Authorization" in request.headers:
		raise MobileError("mixed_authentication")
	account = frappe.session.user
	login_manager = getattr(frappe.local, "login_manager", None)
	sid = request.cookies.get("sid")
	if (
		not account
		or account == "Guest"
		or account != getattr(login_manager, "user", None)
		or not sid
		or sid != frappe.session.sid
	):
		raise MobileError("pwa_session_required", 401)

	origin = request.headers.get("Origin")
	csrf_token = request.headers.get("X-Frappe-CSRF-Token", "")
	expected_csrf = frappe.session.data.csrf_token
	if origin != request.host_url.rstrip("/") or not expected_csrf or not compare_digest(
		csrf_token.encode(), expected_csrf.encode()
	):
		raise MobileError("pwa_request_forbidden", 403)

	try:
		created = datetime.fromisoformat(str(frappe.session.data.creation))
	except ValueError as error:
		raise MobileError("pwa_session_required", 401) from error
	issued_at = int(created.replace(tzinfo=ZoneInfo(get_system_timezone())).timestamp())
	principal = content_digest(["pwa", account])
	return _sync_payload(request, Identity(frappe.local.site, account, principal, "pwa", issued_at, None))


def _sync_payload(request, identity):
	app_version = request.headers.get("X-Mobile-App-Version", "")
	contract_version = request.headers.get("X-Mobile-Contract-Version", "")
	if not APP_VERSION.fullmatch(app_version) or not CONTRACT_VERSION.fullmatch(contract_version):
		raise MobileError("invalid_client_version")
	_limit_and_count(identity.principal, app_version, contract_version)
	if contract_version != "1":
		raise MobileError("unsupported_contract_version")
	body = _read_json(request)
	if "cmd" in body:
		raise MobileError("invalid_mobile_route")
	return identity, body


def identity_sync_request():
	request = frappe.local.request
	if (
		request.path != "/api/method/platform_core.api.mobile.revoke_user_installations"
		or "cmd" in request.args
	):
		raise MobileError("invalid_mobile_route")
	auth = request.headers.get("Authorization", "").split()
	if len(auth) != 2 or auth[0].lower() != "bearer":
		raise MobileError("service_token_required", 403)
	login_manager = getattr(frappe.local, "login_manager", None)
	if request.cookies.get("sid") not in (None, "", "Guest") and getattr(
		login_manager, "user", "Guest"
	) not in (None, "Guest"):
		raise MobileError("service_token_required", 403)

	# Only the identity auth hook may set these verified claims.
	claims = getattr(frappe.local, "kimlik_service_claims", None)
	if not isinstance(claims, dict) or claims.get("azp") != "identity-sync":
		raise MobileError("service_token_required", 403)
	body = _read_json(request)
	if "cmd" in body:
		raise MobileError("invalid_mobile_route")
	if body.keys() != {"issuer", "subject"} or any(
		not isinstance(body[field], str)
		or not 1 <= len(body[field]) <= limit
		or body[field] != body[field].strip()
		for field, limit in (("issuer", 512), ("subject", 255))
	):
		raise MobileError("invalid_request")
	if body["issuer"] != claims.get("iss"):
		raise MobileError("service_token_required", 403)
	return body


def _error_response(error):
	frappe.db.rollback()
	frappe.local.response["http_status_code"] = error.status
	frappe.local.response["code"] = error.code
	if error.code == "IdentityNotFound":
		frappe.local.response["exc_type"] = error.code
	if error.status == 503:
		frappe.local.response_headers.setdefault("Retry-After", "1")
	if error.current is not None:
		frappe.local.response["current"] = error.current
	return None


def endpoint_response(endpoint, action):
	try:
		identity, body = mobile_request(endpoint)
	except MobileError as error:
		return _error_response(error)

	return run_transaction(action, identity, body)


def pwa_endpoint_response(endpoint, action):
	session = getattr(frappe.local, "session_obj", None)
	# Frappe 16 schedules a refresh when this request-local object is present.
	# Background sync must not extend the interactive browser session.
	frappe.local.session_obj = None
	try:
		identity, body = pwa_request(endpoint)
	except MobileError as error:
		return _error_response(error)
	result = run_transaction(action, identity, body)
	if endpoint == "v1_activity" and result is not None:
		frappe.local.session_obj = session
	return result


def identity_sync_response(action):
	try:
		body = identity_sync_request()
	except MobileError as error:
		return _error_response(error)
	return run_transaction(action, body)


def run_transaction(action, *args):
	# MariaDB can reject a locking read when auth opened an older snapshot.
	# Roll back the entire attempt before rerunning database-only commands.
	for attempt in range(3):
		try:
			return action(*args)
		except MobileError as error:
			return _error_response(error)
		except frappe.QueryTimeoutError:
			break
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt < 2:
				# Let other writers finish before reopening the transaction.
				time.sleep(random.uniform(0.03, 0.12) * 2**attempt)

	return _error_response(MobileError("mobile_busy", 503))
