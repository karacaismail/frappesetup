"""Site-scoped quota, budget and attempt records."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import frappe
from frappe.utils import now_datetime
from pypika.functions import Cast

MILLION = Decimal("1000000")
UNSETTLED = ("pending", "unknown", "upstream", "timeout", "invalid_response", "rejected")
POTENTIALLY_BILLED = (*UNSETTLED, "success", "resolved")
USAGE_PAGE_SIZE = 500


def price(model, input_tokens, output_tokens):
	if not model.prices_known or input_tokens is None or output_tokens is None:
		return None
	return (
		Decimal(str(model.input_price)) * input_tokens + Decimal(str(model.output_price)) * output_tokens
	) / MILLION


def money_as_text(table, field):
	# Frappe's MariaDB driver converts DECIMAL columns to Python float.
	return Cast(table[field], "CHAR").as_(field)


def _usage(filters):
	log = frappe.qb.DocType("AI Usage Log")
	fields = [
		"name",
		"input_tokens",
		"output_tokens",
		"usage_known",
		money_as_text(log, "cost"),
		"currency",
		"result",
		"cost_known",
		money_as_text(log, "reserved_cost"),
		"reservation_known",
		"reserved_tokens",
	]
	while True:
		page = frappe.qb.get_query(
			"AI Usage Log", filters=filters, fields=fields, order_by="name asc", limit=USAGE_PAGE_SIZE
		).run(as_dict=True)
		yield from page
		if len(page) < USAGE_PAGE_SIZE:
			return
		filters = {**filters, "name": [">", page[-1].name]}


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
	spent = Decimal(0)
	for item in records:
		if item.currency != account.currency:
			return Decimal(0)
		if item.result not in UNSETTLED and item.cost_known:
			spent += Decimal(str(item.cost))
		elif item.reservation_known:
			spent += Decimal(str(item.reserved_cost))
		else:
			return Decimal(0)
	return Decimal(str(account.monthly_budget)) - spent


def site_quota(user):
	limit = frappe.conf.get("model_gateway_user_requests_per_minute", 30)
	return type(limit) is int and limit > frappe.db.count(
		"AI Usage Log",
		{"user": user, "attempted_at": [">=", now_datetime() - timedelta(minutes=1)]},
	)


def api_quota(api, conservative_tokens):
	if not (api.requests_per_minute or api.tokens_per_minute):
		return True
	filters = {"api": api.name, "attempted_at": [">=", now_datetime() - timedelta(minutes=1)]}
	tokens = conservative_tokens
	if api.tokens_per_minute and tokens > api.tokens_per_minute:
		return False
	for count, item in enumerate(_usage(filters), 1):
		if api.requests_per_minute and count >= api.requests_per_minute:
			return False
		if api.tokens_per_minute and item.result in POTENTIALLY_BILLED:
			if not item.usage_known and not item.reserved_tokens:
				return False
			tokens += item.input_tokens + item.output_tokens if item.usage_known else item.reserved_tokens
			if tokens > api.tokens_per_minute:
				return False
	return True


def begin(route, api, account, provider, model, *, cost, tokens):
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
			"reserved_cost": cost if cost is not None else 0,
			"reservation_known": int(cost is not None),
			"reserved_tokens": tokens,
		}
	)
	log.db_insert()
	# Keep the reservation even if a later attempt or the request fails.
	frappe.db.commit()  # nosemgrep
	return log.name


def is_pending(name):
	"""Use a fresh snapshot so a reconciled attempt cannot start another network request."""
	frappe.db.commit()  # nosemgrep
	return frappe.db.get_value("AI Usage Log", name, "result") == "pending"


def finish(name, model, result, duration_ms, usage=None, *, failure_code=None):
	usage = usage or {}
	tokens_in, tokens_out = usage.get("input"), usage.get("output")
	cost = price(model, tokens_in, tokens_out)
	frappe.db.set_value(
		"AI Usage Log",
		{"name": name, "result": "pending"},
		{
			"result": result,
			"duration_ms": duration_ms,
			"failure_code": failure_code,
			"input_tokens": tokens_in or 0,
			"output_tokens": tokens_out or 0,
			"cost": cost or 0,
			"usage_known": int(tokens_in is not None and tokens_out is not None),
			"cost_known": int(cost is not None),
		},
	)
	frappe.db.commit()  # nosemgrep
