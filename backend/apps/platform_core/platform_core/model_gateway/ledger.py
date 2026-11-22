"""Site-scoped quota, budget and attempt records."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import frappe
from frappe.utils import now_datetime

MILLION = Decimal("1000000")
POTENTIALLY_BILLED = ("pending", "success", "upstream", "timeout", "invalid_response", "rejected")


def price(model, input_tokens, output_tokens):
	if not model.prices_known or input_tokens is None or output_tokens is None:
		return None
	return (
		Decimal(str(model.input_price)) * input_tokens + Decimal(str(model.output_price)) * output_tokens
	) / MILLION


def _usage(filters):
	return frappe.get_all(
		"AI Usage Log",
		filters=filters,
		fields=["input_tokens", "output_tokens", "usage_known", "cost", "currency", "result", "cost_known"],
	)


def remaining(account):
	if not account.has_monthly_budget:
		return None
	month = now_datetime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
	records = _usage(
		{
			"account": account.name,
			"attempted_at": [">=", month],
			"result": ["in", POTENTIALLY_BILLED],
		}
	)
	if any(not item.cost_known or item.currency != account.currency for item in records):
		return Decimal(0)
	return Decimal(str(account.monthly_budget)) - sum(Decimal(str(item.cost)) for item in records)


def site_quota(user):
	limit = frappe.conf.get("model_gateway_user_requests_per_minute", 30)
	return type(limit) is int and limit > frappe.db.count(
		"AI Usage Log",
		{"user": user, "attempted_at": [">=", now_datetime() - timedelta(minutes=1)]},
	)


def api_quota(api, conservative_tokens):
	if not (api.requests_per_minute or api.tokens_per_minute):
		return True
	records = _usage({"api": api.name, "attempted_at": [">=", now_datetime() - timedelta(minutes=1)]})
	if api.requests_per_minute and len(records) >= api.requests_per_minute:
		return False
	if api.tokens_per_minute:
		billable = [item for item in records if item.result in POTENTIALLY_BILLED]
		if any(not item.usage_known for item in billable):
			return False
		tokens = sum(item.input_tokens + item.output_tokens for item in billable)
		return tokens + conservative_tokens <= api.tokens_per_minute
	return True


def begin(route, api, account, provider, model):
	# This internal audit writer only inserts fields assembled from authorized records.
	# No caller can supply values directly or grant creation rights to their REST identity.
	log = frappe.get_doc(
		{
			"doctype": "AI Usage Log",
			"name": uuid4().hex,
			"attempted_at": now_datetime(),
			"user": frappe.session.user,
			"route": route,
			"provider": provider.name,
			"account": account.name,
			"api": api.name,
			"model": model.name,
			"currency": model.cost_currency,
			"result": "pending",
			"usage_known": 0,
		}
	)
	log.db_insert()
	# Keep the reservation even if a later attempt or the request fails.
	frappe.db.commit()  # nosemgrep
	return log.name


def finish(name, model, result, duration_ms, usage=None):
	usage = usage or {}
	tokens_in, tokens_out = usage.get("input"), usage.get("output")
	cost = price(model, tokens_in, tokens_out)
	frappe.db.set_value(
		"AI Usage Log",
		name,
		{
			"result": result,
			"duration_ms": duration_ms,
			"input_tokens": tokens_in or 0,
			"output_tokens": tokens_out or 0,
			"cost": cost or 0,
			"usage_known": int(tokens_in is not None and tokens_out is not None),
			"cost_known": int(cost is not None),
		},
	)
	frappe.db.commit()  # nosemgrep
