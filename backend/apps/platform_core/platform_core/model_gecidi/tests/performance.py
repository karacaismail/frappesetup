"""Measure O-31 on an isolated Frappe site with a real loopback HTTP provider."""

import json
from contextvars import ContextVar
from datetime import date, timedelta
from math import ceil
from time import perf_counter
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

import frappe
from frappe.utils import now_datetime
from frappe.utils.password import set_encrypted_password

from platform_core.model_gecidi import adapters
from platform_core.model_gecidi.tests.http_fixture import TEST_SITE, _configured_fixture

SAMPLES = 50
READ_MS = 500
WRITE_MS = 1000
_provider_seconds = ContextVar("gateway_benchmark_provider_seconds", default=None)


def _p95(values):
	return sorted(values)[ceil(0.95 * len(values)) - 1] * 1000


def summarize(samples, *, limit_ms):
	if len(samples) < SAMPLES:
		raise ValueError("O-31 needs at least 50 samples per operation.")
	provider = _p95([provider for _total, provider in samples])
	gateway = _p95([max(0, total - provider) for total, provider in samples])
	return {
		"samples": len(samples),
		"gateway_p95_ms": round(gateway, 3),
		"http_server_p95_ms": round(_p95([total for total, _provider in samples]), 3),
		"provider_p95_ms": round(provider, 3),
		"limit_ms": limit_ms,
		"pass": gateway <= limit_ms,
	}


def _measure_http(application):
	def serve(environ, start_response):
		started = perf_counter()
		marker = _provider_seconds.set(0.0)

		def respond(status, headers, exc_info=None):
			timing = f"{perf_counter() - started:.9f},{_provider_seconds.get():.9f}"
			return start_response(status, [*headers, ("X-Gateway-Benchmark", timing)], exc_info)

		try:
			return application(environ, respond)
		finally:
			_provider_seconds.reset(marker)

	return serve


def _measure_transport(post):
	def measured(*args, **kwargs):
		preflight_seconds = 0.0
		before_post = kwargs.get("before_post")

		def check_reservation():
			nonlocal preflight_seconds
			started = perf_counter()
			try:
				return before_post()
			finally:
				preflight_seconds += perf_counter() - started

		if before_post is not None:
			kwargs["before_post"] = check_reservation
		started = perf_counter()
		try:
			return post(*args, **kwargs)
		finally:
			previous = _provider_seconds.get()
			if previous is not None:
				_provider_seconds.set(previous + perf_counter() - started - preflight_seconds)

	return measured


def _prepare_load():
	if not frappe.db.exists("DocType", "Leave Application"):
		raise RuntimeError("Install HRMS on the disposable benchmark site first.")
	if frappe.db.count("Employee") or frappe.db.count("Leave Application"):
		raise RuntimeError("The benchmark requires a site without existing employees or leave records.")
	suffix = uuid4().hex[:8]
	employees = [f"Gateway Bench {suffix}-{index:04d}" for index in range(200)]
	days = [date(2026, 1, 1) + timedelta(days=index) for index in range(10)]
	frappe.db.bulk_insert(
		"Employee",
		["name", "first_name", "employee_name", "status"],
		[(name, name, name, "Active") for name in employees],
	)
	frappe.db.bulk_insert(
		"Leave Application",
		["name", "employee", "employee_name", "from_date", "to_date", "status", "docstatus"],
		[
			(f"{employee}-{index:02d}", employee, employee, day, day, "Open", 0)
			for employee in employees
			for index, day in enumerate(days)
		],
	)
	frappe.db.commit()
	return employees


def _usage(fixture, result, attempted_at):
	return (
		frappe.get_doc(
			doctype="AI Usage Log",
			name=str(uuid4()),
			attempted_at=attempted_at,
			user=fixture["users"]["manager"],
			provider=frappe.db.get_value("AI Account", fixture["second_account"], "provider"),
			account=fixture["second_account"],
			api=fixture["second_api"],
			model=fixture["model"],
			result=result,
			currency="USD",
			duration_ms=0,
		)
		.insert()
		.name
	)


def _sample(fixture, method, path, payload=None, *, actor="manager"):
	response = fixture["sessions"][actor].request(
		method, fixture["base"] + path, json=payload, timeout=15, allow_redirects=False
	)
	if response.status_code != 200:
		raise RuntimeError(
			f"Benchmark operation {path.rsplit('/', 1)[-1]} returned HTTP {response.status_code}."
		)
	return response.json(), tuple(map(float, response.headers["X-Gateway-Benchmark"].split(",")))


def _collect(fixture):
	provider = frappe.db.get_value("AI Account", fixture["second_account"], "provider")
	old = now_datetime() - timedelta(days=366)
	rpc = "/api/method/platform_core.api.model."
	samples = {}
	purged = []

	def record(group, operation, method, path, payload=None, *, actor="manager"):
		body, sample = _sample(fixture, method, path, payload, actor=actor)
		samples.setdefault((group, operation), []).append(sample)
		return body

	try:
		for _sample_index in range(SAMPLES):
			unknown = _usage(fixture, "unknown", now_datetime())
			expired = _usage(fixture, "success", old)
			set_encrypted_password("AI API", fixture["clearable_api"], fixture["credential"], "api_key")
			frappe.db.set_value("AI API", fixture["clearable_api"], "enabled", 0)
			frappe.db.commit()
			for doctype, name in (
				("AI Provider", provider),
				("AI Account", fixture["second_account"]),
				("AI API", fixture["second_api"]),
				("AI Model", fixture["model"]),
				("AI Route", fixture["role_route"]),
				("AI Usage Log", unknown),
			):
				path = f"/api/resource/{quote(doctype, safe='')}"
				record("read", f"{doctype} list", "GET", path + "?limit_page_length=20")
				record("read", f"{doctype} detail", "GET", f"{path}/{quote(str(name), safe='')}")
			record(
				"write",
				"complete",
				"POST",
				rpc + "complete",
				{
					"route": fixture["role_route"],
					"messages": [{"role": "user", "content": "Benchmark fixture"}],
					"limit": 12,
				},
			)
			record(
				"write",
				"test_api",
				"POST",
				rpc + "test_api",
				{
					"api": fixture["second_api"],
					"model": fixture["model"],
				},
			)
			record(
				"write",
				"resolve_usage",
				"POST",
				rpc + "resolve_usage",
				{
					"log": unknown,
					"cost": "0.001",
					"currency": "USD",
				},
			)
			preview = record("read", "purge_preview", "POST", rpc + "purge_usage", actor="system_manager")[
				"message"
			]
			if preview["targets"] != [expired]:
				raise RuntimeError("The benchmark may only delete its own fixture record.")
			purged.append(expired)
			record(
				"write",
				"purge_usage",
				"POST",
				rpc + "purge_usage",
				{
					"dry_run": False,
					"preview_token": preview["preview_token"],
				},
				actor="system_manager",
			)
			record(
				"write",
				"clear_api_credential",
				"POST",
				rpc + "clear_api_credential",
				{
					"api": fixture["clearable_api"],
				},
			)
	finally:
		frappe.db.delete(
			"Activity Log",
			{
				"user": fixture["users"]["system_manager"],
				"subject": "Model gateway usage logs purged",
			},
		)
		if purged:
			frappe.db.delete(
				"Deleted Document", {"deleted_doctype": "AI Usage Log", "deleted_name": ["in", purged]}
			)
		frappe.db.commit()
	return {
		f"{group}:{operation}": summarize(timings, limit_ms=READ_MS if group == "read" else WRITE_MS)
		for (group, operation), timings in samples.items()
	}


def run():
	"""Run the manual benchmark. Emit JSON and fail if any p95 threshold is exceeded."""
	if frappe.local.site != TEST_SITE or not frappe.conf.get("allow_tests"):
		raise RuntimeError("Use the disposable gateway test site.")
	if frappe.conf.get("model_gateway_user_requests_per_minute", 30) <= 2 * SAMPLES:
		raise RuntimeError("Increase the gateway quota on the disposable site for the measurement.")
	employees = _prepare_load()
	try:
		with (
			patch.object(adapters, "_post_json", _measure_transport(adapters._post_json)),
			_configured_fixture(_measure_http) as fixture,
		):
			results = _collect(fixture)
	finally:
		frappe.db.delete("Leave Application", {"employee": ["in", employees]})
		frappe.db.delete("Employee", {"name": ["in", employees]})
		frappe.db.commit()
	report = {"employees": len(employees), "leave_records": 10 * len(employees), "operations": results}
	print(json.dumps(report))
	if any(not result["pass"] for result in results.values()):
		raise RuntimeError("A gateway operation exceeded its O-31 p95 limit.")
	return report
