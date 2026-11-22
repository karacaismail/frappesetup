"""Resolve tenant routes and dispatch bounded provider attempts."""

import json
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from math import ceil
from time import monotonic, time
from uuid import UUID

import frappe
from frappe.utils.password import get_decrypted_password
from redis.exceptions import LockError, RedisError

from platform_core.model_gecidi import adapters, ledger, policy, routing
from platform_core.model_gecidi.policy import Denied

COOLDOWN = 60
MAX_ROUTE_SECONDS = 60
LOCK_SECONDS = 10
STALE_ATTEMPT_SECONDS = 135
RESPONSE_OVERHEAD_SECONDS = 8
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
		kind, addresses, oauth_addresses = policy.connection_policy(self.base_url, self.oauth_url)
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
			kind=kind,
			addresses=addresses,
			oauth_addresses=oauth_addresses,
		)


def _json(value):
	return json.loads(value) if isinstance(value, str) else value or []


def _valid_name(name):
	return isinstance(name, str) and 0 < len(name) <= 140


def _document(doctype, name):
	if not _valid_name(name):
		raise Denied(400, "invalid_request")
	try:
		return frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		raise frappe.PermissionError from None


def _target(api_id, model_id):
	api = _document("AI API", api_id)
	model = _document("AI Model", model_id)
	account = _document("AI Account", api.account)
	provider = _document("AI Provider", account.provider)
	return _checked_target(api, account, provider, model)


def _checked_target(api, account, provider, model):
	models = _json(api.allowed_models)
	if model.provider != provider.name or (models and model.model_id not in models):
		raise Denied(400, "invalid_target")
	return Target(api, account, provider, model)


def _record_key(name):
	# The database can return the canonical spelling of a UUID link.
	try:
		return str(UUID(str(name)))
	except ValueError:
		return name


def _selection_rows(doctype, names, fields):
	names = list(dict.fromkeys(name for name in names if _valid_name(name)))
	if not names:
		return {}
	return {
		_record_key(row.name): row
		for row in frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", *fields])
	}


def _selection_row(rows, name):
	if not _valid_name(name):
		raise Denied(400, "invalid_request")
	row = rows.get(_record_key(name))
	if row is None:
		raise frappe.PermissionError
	return row


def _route_targets(items):
	# The route is authorized before this internal read. Selection needs no credentials.
	apis = _selection_rows(
		"AI API",
		(item.api for item in items),
		("account", "allowed_models", "enabled", "health_status", "priority", "weight"),
	)
	models = _selection_rows(
		"AI Model",
		(item.model for item in items),
		(
			"provider",
			"model_id",
			"enabled",
			"context_size",
			"prices_known",
			"input_price",
			"output_price",
			"cost_currency",
			"capabilities",
		),
	)
	accounts = _selection_rows(
		"AI Account",
		(api.account for api in apis.values()),
		("provider", "enabled", "has_monthly_budget", "currency"),
	)
	providers = _selection_rows(
		"AI Provider", (account.provider for account in accounts.values()), ("enabled",)
	)
	targets = []
	for item in items:
		api = _selection_row(apis, item.api)
		model = _selection_row(models, item.model)
		account = _selection_row(accounts, api.account)
		provider = _selection_row(providers, account.provider)
		targets.append(_checked_target(api, account, provider, model))
	return targets


def _cache_key(api):
	return frappe.cache.make_key("model_gateway:cooldown:" + api)


def _choose(targets, route, request):
	available, choices = {}, []
	for target in targets:
		if not target.active or (route and target.api.health_status == "auth_failed"):
			continue
		cost = ledger.price(target.model, input_token_bound(target.model, request), request.limit)
		if target.account.has_monthly_budget and target.account.currency != target.model.cost_currency:
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


def read_timeout(limit, output_tokens_per_second):
	seconds = RESPONSE_OVERHEAD_SECONDS + ceil(limit / output_tokens_per_second)
	if seconds > MAX_ROUTE_SECONDS - CONNECT_SECONDS:
		raise Denied(400, "output_limit_exceeds_deadline")
	return seconds


def input_token_bound(model, request):
	payload = json.dumps([request.messages, request.tools, request.schema], ensure_ascii=False)
	return max(model.context_size, len(payload.encode("utf-8")))


def retry_allowed(code, *, capped):
	return code != "timeout" or not capped


def _set_health(api, status):
	frappe.db.set_value("AI API", api, "health_status", status, update_modified=False)


def _attempt(candidate, target, request, timeout, deadline, log):
	started = monotonic()
	outcome = "not_sent"
	usage = None
	failure_code = None

	def owns_reservation():
		return ledger.is_pending(log)

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
		if code in {"reservation_lost", "endpoint_unavailable"}:
			outcome = "not_sent"
			error = "gateway_unavailable" if code == "reservation_lost" else code
			raise Denied(503, error) from None
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
		retry = retry_allowed(code, capped=target.account.has_monthly_budget)
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
	lock = frappe.cache.lock(key, timeout=timeout)
	try:
		if not lock.acquire(blocking_timeout=0.4):
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


def lock_row(doctype, name, fields):
	# Build a locking read without loading DocType metadata. On MariaDB,
	# a consistent read before the locks would establish an old snapshot.
	table = frappe.qb.DocType(doctype)
	columns = [
		ledger.money_as_text(table, field) if doctype == "AI Account" and field == "monthly_budget" else field
		for field in fields
	]
	rows = frappe.qb.from_(table).select(*columns).where(table.name == name).for_update().run(as_dict=True)
	if not rows:
		raise Denied(503, "provider_unavailable")
	return rows[0]


def _reserve(route, target, request):
	input_tokens = input_token_bound(target.model, request)
	tokens = input_tokens + request.limit
	cost = ledger.price(target.model, input_tokens, request.limit)
	user = frappe.session.user
	# SQL row locks fence the accounting transaction even if a cache lease expires.
	# Keep their order stable and release them before any provider call.
	with scoped_lock("account", target.account.name), scoped_lock("user", user):
		frappe.db.commit()  # nosemgrep
		try:
			account = lock_row(
				"AI Account",
				target.account.name,
				("name", "enabled", "has_monthly_budget", "monthly_budget", "currency"),
			)
			api = lock_row(
				"AI API",
				target.api.name,
				("name", "account", "modified", "enabled", "requests_per_minute", "tokens_per_minute"),
			)
			if not (
				account.enabled
				and api.enabled
				and api.account == account.name
				and api.modified == target.api.modified
			):
				raise Denied(503, "provider_unavailable")
			if not lock_row("User", user, ("enabled",)).enabled:
				raise Denied(401, "authentication_required")
			budget = ledger.remaining(account)
			if budget is not None and (
				budget <= 0 or cost is None or cost > budget or account.currency != target.model.cost_currency
			):
				raise Denied(503, "provider_unavailable")
			if not ledger.api_quota(api, tokens) or not ledger.site_quota(user):
				raise Denied(429, "quota_exceeded")
			return ledger.begin(
				route.name if route else None,
				api,
				account,
				target.provider,
				target.model,
				cost=cost,
				tokens=tokens,
			)
		except Exception:
			frappe.db.rollback()
			raise


def _dispatch(route, targets, request, deadline):
	failed_apis = set()
	last_denial = None
	for candidate, target in _choose(targets, route, request):
		if target.api.name in failed_apis:
			continue
		try:
			current = _target(target.api.name, target.model.name)
		except (Denied, frappe.PermissionError) as failure:
			last_denial = failure
			continue
		try:
			choices = _choose([current], route, request)
			if not choices:
				continue
			candidate, current = choices[0]
			timeout = read_timeout(request.limit, current.model.output_tokens_per_second or 30)
			if timeout > deadline - monotonic() - CONNECT_SECONDS:
				last_denial = Denied(503, "provider_unavailable")
				continue
			outbound = policy.outbound(current.base_url, current.oauth_url, route, request)
			log = _reserve(route, current, outbound)
			result, retry = _attempt(candidate, current, outbound, timeout, deadline, log)
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
	deadline = monotonic() + MAX_ROUTE_SECONDS
	policy.require_user()
	_require_clean_transaction()
	request = policy.parse(messages, tools, schema, limit)
	route = _document("AI Route", route)
	policy.require_route(route)
	if len(route.targets) > MAX_TARGETS:
		raise Denied(400, "invalid_route")
	targets = _route_targets(route.targets)
	try:
		return _dispatch(route, targets, request, deadline)
	except RedisError:
		raise Denied(503, "gateway_unavailable") from None


def test_api(api, model):
	deadline = monotonic() + MAX_ROUTE_SECONDS
	policy.require_user(managers_only=True)
	_require_clean_transaction()
	target = _target(api, model)
	request = policy.Request([{"role": "user", "content": "Reply with OK."}], [], None, 8)
	try:
		return _dispatch(None, [target], request, deadline)
	except RedisError:
		raise Denied(503, "gateway_unavailable") from None
