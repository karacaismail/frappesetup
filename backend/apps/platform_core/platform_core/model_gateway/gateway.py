"""Resolve tenant routes and dispatch bounded provider attempts."""

import json
import secrets
from dataclasses import dataclass
from time import monotonic, time

import frappe
from redis.exceptions import LockError, RedisError

from platform_core.model_gateway import adapters, agent_access, ledger, policy, routing
from platform_core.model_gateway.policy import Denied

COOLDOWN = 60
MAX_ROUTE_SECONDS = 120
MAX_ATTEMPT_TIMEOUT = 10
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
			self.api.get_password("api_key", raise_exception=False) if self.api.auth_type != "none" else ""
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


def _attempt(route, candidate, target, request, timeout, lock):
	endpoint = target.endpoint()
	started = monotonic()
	log = ledger.begin(
		route.name if route else None, target.api, target.account, target.provider, target.model
	)
	if not lock.owned():
		raise Denied(503, "gateway_unavailable")
	try:
		result = adapters.complete(
			endpoint,
			target.model.model_id,
			request.messages,
			request.limit,
			tools=request.tools,
			schema=request.schema,
			timeout=timeout,
			before_post=lock.owned,
		)
	except adapters.GatewayError as failure:
		if failure.code == "reservation_lost":
			raise Denied(503, "gateway_unavailable") from None
		decision = routing.on_failure(candidate, failure.code, now=time(), cooldown_seconds=COOLDOWN)
		if not decision.candidate.enabled:
			frappe.db.set_value("AI API", target.api.name, "health_status", "auth_failed")
		elif decision.candidate.cooldown_until:
			frappe.db.set_value("AI API", target.api.name, "health_status", "unhealthy")
			frappe.cache.set(_cache_key(target.api.name), decision.candidate.cooldown_until, ex=COOLDOWN)
		ledger.finish(log, target.model, failure.code, int((monotonic() - started) * 1000))
		return None, decision.try_next
	if target.api.health_status != "healthy":
		frappe.db.set_value("AI API", target.api.name, "health_status", "healthy")
	ledger.finish(log, target.model, "success", int((monotonic() - started) * 1000), result["usage"])
	return result, False


def _dispatch(route, targets, request, lock, deadline):
	failed_apis = set()
	quota_limited = False
	policy_denied = False
	for candidate, target in _choose(targets, route, request):
		if target.api.name in failed_apis:
			continue
		if not ledger.site_quota(frappe.session.user):
			raise Denied(429, "quota_exceeded")
		# A prior failed attempt can consume the same account's budget. Read anew
		# after recording it, before sending another request against that account.
		budget = ledger.remaining(target.account)
		if budget is not None and (budget <= 0 or candidate.cost is None or candidate.cost > budget):
			continue
		if not ledger.api_quota(target.api, target.model.context_size + request.limit):
			quota_limited = True
			continue
		try:
			outbound = policy.outbound(target.base_url, target.oauth_url, route, request)
		except Denied as failure:
			if route is None:
				raise
			policy_denied |= failure.status == 403
			continue
		timeout = min(MAX_ATTEMPT_TIMEOUT, (deadline - monotonic()) / 2)
		if timeout <= 0:
			break
		result, retry = _attempt(route, candidate, target, outbound, timeout, lock)
		if result is not None:
			return result
		if not retry:
			break
		failed_apis.add(target.api.name)
	if quota_limited:
		raise Denied(429, "quota_exceeded")
	if policy_denied:
		raise Denied(403, "data_policy_denied")
	raise Denied(503, "provider_unavailable")


def _under_lock(call, *args):
	# A tenant-scoped, nonblocking lock serializes the reservation and settlement.
	# Refresh the site's DB snapshot before checking quotas.
	lock = frappe.cache.lock(frappe.cache.make_key("model_gateway:dispatch"), timeout=150, blocking=False)
	try:
		if not lock.acquire():
			raise Denied(429, "gateway_busy")
		try:
			frappe.db.commit()  # nosemgrep
			return call(*args, lock=lock, deadline=monotonic() + MAX_ROUTE_SECONDS)
		finally:
			try:
				lock.release()
			except LockError:
				# A durable attempt was already recorded. Releasing an expired
				# lease must not change its response or release a new owner's lock.
				pass
	except RedisError:
		raise Denied(503, "gateway_unavailable") from None


def _complete(route_id, request, *, lock, deadline):
	route = _document("AI Route", route_id)
	policy.require_route(route)
	pairs = _json(route.targets)
	if len(pairs) > MAX_TARGETS:
		raise Denied(400, "invalid_route")
	targets = [_target(item["api"], item["model"]) for item in pairs]
	return _dispatch(route, targets, request, lock, deadline)


def complete(route, messages, tools, schema, limit):
	policy.require_session()
	if agent_access.is_agent() and not agent_access.spend_call():
		raise Denied(429, "agent_quota_exceeded")
	request = policy.parse(messages, tools, schema, limit)
	return _under_lock(_complete, route, request)


def _test_api(api, model, *, lock, deadline):
	target = _target(api, model)
	request = policy.Request([{"role": "user", "content": "Reply with OK."}], [], None, 8)
	return _dispatch(None, [target], request, lock, deadline)


def test_api(api, model):
	policy.require_session(managers_only=True)
	return _under_lock(_test_api, api, model)
