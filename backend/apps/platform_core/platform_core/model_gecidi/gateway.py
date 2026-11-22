"""Resolve tenant routes and dispatch bounded provider attempts."""

import json
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from time import monotonic, time

import frappe
from frappe.utils.password import get_decrypted_password
from redis.exceptions import LockError, RedisError

from platform_core.model_gecidi import adapters, ledger, policy, routing
from platform_core.model_gecidi.policy import Denied

COOLDOWN = 60
MAX_ROUTE_SECONDS = 105
LOCK_SECONDS = 135
CONNECT_SECONDS = 5
MAX_TARGETS = 12


@dataclass(frozen=True)
class Target:
	api: object
	account: object
	provider: object
	model: object

	@property
	def active(self):
		return self.api.enabled and self.account.enabled and self.provider.enabled and self.model.enabled

	@property
	def base_url(self):
		return self.api.base_url or self.provider.default_url

	@property
	def oauth_url(self):
		return self.api.oauth_token_url if self.api.auth_type == "oauth_client_credentials" else ""

	def endpoint(self):
		secret = (
			get_decrypted_password("AI API", self.api.name, "api_key", raise_exception=False)
			if self.api.auth_type != "none"
			else ""
		)
		return adapters.Endpoint(
			self.api.name,
			self.provider.adapter,
			self.base_url,
			self.api.auth_type,
			secret or "",
			self.oauth_url,
			self.api.oauth_client_id or "",
		)


def _json(value):
	return json.loads(value) if isinstance(value, str) else value or []


def _document(doctype, name):
	if not isinstance(name, str) or not 0 < len(name) <= 140:
		raise Denied(400, "invalid_request")
	try:
		return frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		raise Denied(403, "permission_denied") from None


def _target(api_id, model_id):
	api = _document("AI API", api_id)
	model = _document("AI Model", model_id)
	account = _document("AI Account", api.account)
	provider = _document("AI Provider", account.provider)
	models = _json(api.allowed_models)
	if model.provider != provider.name or (models and model.model_id not in models):
		raise Denied(400, "invalid_target")
	return Target(api, account, provider, model)


def _cache_key(api):
	return frappe.cache.make_key("model_gateway:cooldown:" + api)


def _choose(targets, route, request):
	available, choices = {}, []
	for target in targets:
		if not target.active or (route and target.api.health_status == "auth_failed"):
			continue
		cost = ledger.price(target.model, target.model.context_size, request.limit)
		remaining = ledger.remaining(target.account)
		if remaining is not None and target.account.currency != target.model.cost_currency:
			continue
		if route and route.selection_mode == "cost" and target.model.cost_currency != route.cost_currency:
			continue
		api = target.api
		deadline = frappe.cache.get(_cache_key(api.name))
		entry = routing.Candidate(
			api.name,
			target.model.name,
			priority=api.priority,
			weight=api.weight,
			cost=cost,
			remaining_budget=remaining,
			cooldown_until=float(deadline or 0),
			capabilities=frozenset(_json(target.model.capabilities)),
		)
		choices.append(entry)
		available[(entry.api, entry.model)] = target
	sorted_choices = routing.candidates(
		choices,
		now=time(),
		mode=route.selection_mode if route else "priority",
		required=frozenset(_json(route.required_capabilities)) if route else frozenset(),
		seed=secrets.randbits(64),
	)
	return [(choice, available[(choice.api, choice.model)]) for choice in sorted_choices]


def read_timeout(limit):
	return min(95, 8 + limit / 128)


def retry_allowed(code, *, potentially_billed, capped):
	return code != "timeout" or not potentially_billed or not capped


def _set_health(api, status):
	frappe.db.set_value("AI API", api, "health_status", status, update_modified=False)


def _attempt(candidate, target, request, timeout, deadline, lock, log):
	started = monotonic()
	outcome = "not_sent"
	usage = None
	failure_code = None

	def owns_reservation():
		try:
			return lock.owned()
		except RedisError:
			return False

	try:
		if not owns_reservation():
			raise Denied(503, "gateway_unavailable")
		endpoint = target.endpoint()
		# Beyond this point an unexpected interruption can leave delivery uncertain.
		outcome = "unknown"
		result = adapters.complete(
			endpoint,
			target.model.model_id,
			request.messages,
			request.limit,
			tools=request.tools,
			schema=request.schema,
			timeout=timeout,
			connect_timeout=CONNECT_SECONDS,
			deadline=deadline,
			before_post=owns_reservation,
		)
		outcome, usage = "success", result["usage"]
		if target.api.health_status != "healthy":
			_set_health(target.api.name, "healthy")
		return result, False
	except adapters.GatewayError as failure:
		code = failure_code = failure.code
		if code == "reservation_lost":
			outcome = "not_sent"
			raise Denied(503, "gateway_unavailable") from None
		if failure.may_be_billed:
			outcome = "unknown"
		elif code in ledger.UNSETTLED:
			outcome = "not_billed"
		else:
			outcome = code
		decision = routing.on_failure(candidate, code, now=time(), cooldown_seconds=COOLDOWN)
		if not decision.candidate.enabled:
			_set_health(target.api.name, "auth_failed")
		elif decision.candidate.cooldown_until:
			_set_health(target.api.name, "unhealthy")
			frappe.cache.set(_cache_key(target.api.name), decision.candidate.cooldown_until, ex=COOLDOWN)
		retry = retry_allowed(
			code,
			potentially_billed=failure.may_be_billed,
			capped=target.account.has_monthly_budget,
		)
		return None, retry and decision.try_next
	finally:
		ledger.finish(
			log,
			target.model,
			outcome,
			int((monotonic() - started) * 1000),
			usage,
			failure_code=failure_code,
		)


@contextmanager
def scoped_lock(scope, identity, *, timeout=LOCK_SECONDS):
	key = frappe.cache.make_key(f"model_gateway:{scope}:{identity}")
	lock = frappe.cache.lock(key, timeout=timeout, blocking=False)
	try:
		if not lock.acquire():
			raise Denied(429, "gateway_busy")
		try:
			yield lock
		finally:
			try:
				lock.release()
			except (LockError, RedisError):
				pass
	except RedisError:
		raise Denied(503, "gateway_unavailable") from None


def _reserve(route, target, candidate, tokens):
	budget = ledger.remaining(target.account)
	if budget is not None and (budget <= 0 or candidate.cost is None or candidate.cost > budget):
		raise Denied(503, "provider_unavailable")
	if not ledger.api_quota(target.api, tokens):
		raise Denied(429, "quota_exceeded")
	user = frappe.session.user
	with scoped_lock("user", user, timeout=10):
		# This is a gateway-owned transaction. Refresh the snapshot under the lock.
		frappe.db.commit()  # nosemgrep
		if not ledger.site_quota(user):
			raise Denied(429, "quota_exceeded")
		return ledger.begin(
			route.name if route else None,
			target.api,
			target.account,
			target.provider,
			target.model,
			cost=candidate.cost,
			tokens=tokens,
		)


def _dispatch(route, targets, request, deadline):
	failed_apis = set()
	last_denial = None
	for candidate, target in _choose(targets, route, request):
		if target.api.name in failed_apis:
			continue
		timeout = min(read_timeout(request.limit), deadline - monotonic() - CONNECT_SECONDS)
		if timeout <= 0:
			break
		try:
			with scoped_lock("account", target.account.name) as lock:
				# The candidate list is advisory. Re-read after acquiring the account lock.
				frappe.db.commit()  # nosemgrep
				current = _target(target.api.name, target.model.name)
				if current.account.name != target.account.name:
					continue
				choices = _choose([current], route, request)
				if not choices:
					continue
				candidate, current = choices[0]
				outbound = policy.outbound(current.base_url, current.oauth_url, route, request)
				log = _reserve(route, current, candidate, current.model.context_size + request.limit)
				result, retry = _attempt(candidate, current, outbound, timeout, deadline, lock, log)
		except Denied as failure:
			if failure.code == "gateway_unavailable":
				raise
			last_denial = failure
			continue
		if result is not None:
			return result
		if not retry:
			raise Denied(503, "provider_unavailable")
		failed_apis.add(target.api.name)
	if last_denial:
		raise last_denial
	raise Denied(503, "provider_unavailable")


def _require_clean_transaction():
	# Durable reservations must never commit writes belonging to a background caller.
	if frappe.db.transaction_writes:
		raise Denied(409, "transaction_active")


def complete(route, messages, tools=None, schema=None, limit=1024):
	policy.require_user()
	_require_clean_transaction()
	deadline = monotonic() + MAX_ROUTE_SECONDS
	request = policy.parse(messages, tools, schema, limit)
	route = _document("AI Route", route)
	policy.require_route(route)
	pairs = _json(route.targets)
	if len(pairs) > MAX_TARGETS:
		raise Denied(400, "invalid_route")
	targets = [_target(item["api"], item["model"]) for item in pairs]
	try:
		return _dispatch(route, targets, request, deadline)
	except RedisError:
		raise Denied(503, "gateway_unavailable") from None


def test_api(api, model):
	policy.require_user(managers_only=True)
	_require_clean_transaction()
	deadline = monotonic() + MAX_ROUTE_SECONDS
	target = _target(api, model)
	request = policy.Request([{"role": "user", "content": "Reply with OK."}], [], None, 8)
	try:
		return _dispatch(None, [target], request, deadline)
	except RedisError:
		raise Denied(503, "gateway_unavailable") from None
