"""Measure overlapping reservations through real HTTP on the disposable gateway site."""

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
from threading import Barrier, Condition, Event
from types import SimpleNamespace
from unittest.mock import patch

import frappe
import requests

from platform_core.model_gateway import ledger
from platform_core.model_gateway.tests.http_fixture import _configured_fixture

REQUEST_COUNT = 20
REQUEST_LIMIT = 12
BUDGET = Decimal("0.060")
RESERVED_PER_CALL = Decimal("0.012")
SETTLED_PER_CALL = Decimal("0.003")
ADMISSIONS = int(BUDGET / RESERVED_PER_CALL)
MESSAGE_PREFIX = "Concurrency fixture "
COMPLETE_PATH = "/api/method/platform_core.api.model.complete"


def check_reservations(samples):
	if not samples or any(amount > BUDGET for amount in samples):
		raise AssertionError("The committed reservations exceeded the budget or could not be measured.")
	expected = [RESERVED_PER_CALL * count for count in range(1, ADMISSIONS + 1)]
	if samples != expected:
		raise AssertionError("The account did not gain exactly one reservation per admitted request.")


def check_dispatches(successes, provider_messages):
	if Counter(provider_messages) != Counter(successes):
		raise AssertionError("The fake provider did not receive each successful request exactly once.")


def _send_batch(fixture):
	account = fixture["second_account"]
	filters = {"account": account, "result": "pending"}
	release = Event()
	barrier = Barrier(REQUEST_COUNT + 1)
	condition = Condition()
	samples = []
	responses = {}
	reserve = ledger.begin

	def observe_reservation(*args, **kwargs):
		log = reserve(*args, **kwargs)
		# ledger.begin committed the reservation. Hold all fake provider replies so
		# none of these reservations can settle while the other requests compete.
		total = sum((Decimal(row.reserved_cost) for row in ledger._usage(filters)), Decimal(0))
		with condition:
			samples.append(total)
			condition.notify_all()
		return log

	def send(session, index):
		message = f"{MESSAGE_PREFIX}{index}"
		barrier.wait(timeout=8)
		response = session.post(
			fixture["base"] + COMPLETE_PATH,
			json={
				"route": fixture["role_route"],
				"messages": [{"role": "user", "content": message}],
				"limit": REQUEST_LIMIT,
			},
			timeout=15,
		)
		error = response.json().get("message", {}).get("error")
		with condition:
			responses[message] = (response.status_code, error)
			condition.notify_all()

	fixture["provider_server"].provider_gate = lambda _path: release.wait(8)
	try:
		with ExitStack() as resources, patch.object(ledger, "begin", observe_reservation):
			sessions = [resources.enter_context(requests.Session()) for _index in range(REQUEST_COUNT)]
			manager = fixture["sessions"]["manager"]
			for session in sessions:
				session.headers.update(manager.headers)
				session.cookies.update(manager.cookies)
			with ThreadPoolExecutor(max_workers=REQUEST_COUNT) as pool:
				futures = [pool.submit(send, session, index) for index, session in enumerate(sessions)]
				try:
					barrier.wait(timeout=8)
					with condition:
						held = condition.wait_for(
							lambda: len(samples) >= ADMISSIONS
							and len(responses) >= REQUEST_COUNT - ADMISSIONS,
							timeout=5,
						)
					if not held:
						raise AssertionError("The full budget could not be observed with replies held.")
					frappe.db.rollback()
					pending = list(ledger._usage(filters))
					if len(pending) != ADMISSIONS:
						raise AssertionError("The independently read pending count did not match the budget.")
				finally:
					release.set()
				for future in futures:
					future.result()
	finally:
		fixture["provider_server"].provider_gate = None
	return responses, samples


def run():
	"""Race 20 authenticated requests and emit budget and HTTP evidence as JSON."""
	with _configured_fixture() as fixture:
		account = fixture["second_account"]
		frappe.db.set_value("PLT AI Account", account, {"has_monthly_budget": 1, "monthly_budget": BUDGET})
		frappe.db.set_value(
			"PLT AI Model", fixture["model"], {"prices_known": 1, "input_price": 0, "output_price": 1000}
		)
		frappe.db.commit()

		responses, samples = _send_batch(fixture)
		check_reservations(samples)
		statuses = Counter(status for status, _error in responses.values())
		expected_errors = {429: "gateway_busy", 503: "provider_unavailable"}
		if len(responses) != REQUEST_COUNT or any(
			status != 200 and (status not in expected_errors or expected_errors[status] != error)
			for status, error in responses.values()
		):
			raise AssertionError(f"Unexpected gateway responses: {dict(statuses)}")
		successes = {message for message, (status, _error) in responses.items() if status == 200}
		if len(successes) != ADMISSIONS:
			raise AssertionError(f"Expected {ADMISSIONS} successful requests, got {len(successes)}.")
		provider_messages = [
			json.loads(payload)["messages"][0]["content"] for payload in fixture["provider_payloads"]
		]
		check_dispatches(successes, provider_messages)

		frappe.db.rollback()
		settlements = list(ledger._usage({"account": account}))
		expected_cost = ADMISSIONS * SETTLED_PER_CALL
		if (
			len(settlements) != ADMISSIONS
			or len({row.name for row in settlements}) != ADMISSIONS
			or any(
				row.result != "success"
				or not row.cost_known
				or Decimal(row.cost) != SETTLED_PER_CALL
				or Decimal(row.reserved_cost) != RESERVED_PER_CALL
				for row in settlements
			)
		):
			raise AssertionError("A request was settled twice, omitted, or charged the wrong amount.")
		remaining = ledger.remaining(
			SimpleNamespace(name=account, currency="USD", has_monthly_budget=True, monthly_budget=BUDGET)
		)
		if remaining != BUDGET - expected_cost:
			raise AssertionError("The budget double-counted a reservation after settlement.")

		report = {
			"requests": REQUEST_COUNT,
			"status_counts": dict(sorted(statuses.items())),
			"http_503_percent": statuses[503] * 100 / REQUEST_COUNT,
			"currency": "USD",
			"budget": str(BUDGET),
			"committed_reservations": [str(amount) for amount in samples],
			"provider_dispatches": len(provider_messages),
			"settled_logs": len(settlements),
			"settled_cost": str(expected_cost),
			"remaining_budget": str(remaining),
		}
		print(json.dumps(report))
		return report
