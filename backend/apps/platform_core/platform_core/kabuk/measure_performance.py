"""Run the O-31 shell HTTP benchmark on a disposable Frappe site."""

import argparse
import json
import logging
import os
from contextlib import closing, contextmanager
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from math import ceil
from pathlib import Path
from secrets import token_urlsafe
from statistics import median
from threading import Thread
from time import perf_counter_ns
from urllib.parse import urlencode

SITE = "test-kabuk.localhost"
ACCOUNT = "shell-o31@example.test"
EMPLOYEES = 200
LEAVE_PER_EMPLOYEE = 10
SAMPLES = 50
LIMIT_MS = 500
TIMING_HEADER = "X-Shell-Test-Server-Ns"
ENDPOINTS = (
	("Aç\u0131l\u0131ş verisi", "/api/method/platform_core.api.shell.get_bootstrap", "user", ACCOUNT),
	(
		"DocType tan\u0131m\u0131",
		"/api/method/platform_core.api.meta.get_doctype?" + urlencode({"doctype": "Leave Application"}),
		"schema",
		"Leave Application",
	),
)


def summarize(samples):
	if len(samples) < SAMPLES:
		raise ValueError(f"At least {SAMPLES} samples are required.")
	p95 = sorted(samples)[ceil(len(samples) * 0.95) - 1]
	return p95, p95 <= LIMIT_MS


@contextmanager
def test_database():
	import frappe

	frappe.init(SITE)
	try:
		if not frappe.conf.allow_tests:
			raise RuntimeError("Use the disposable test-kabuk.localhost site with allow_tests enabled.")
		frappe.connect()
		frappe.set_user("Administrator")
		yield frappe
	finally:
		frappe.destroy()


def seed_site():
	from frappe.utils import now_datetime

	with test_database() as frappe:
		if not {"erpnext", "hrms", "platform_core"} <= set(frappe.get_installed_apps()):
			raise RuntimeError("Install ERPNext, HRMS and platform_core on the disposable site.")
		if any(frappe.db.count(doctype) for doctype in ("Employee", "Leave Application")):
			raise RuntimeError("The benchmark requires empty Employee and Leave Application tables.")
		password = token_urlsafe(32)
		frappe.get_doc(
			doctype="User",
			email=ACCOUNT,
			first_name="O31 Shell Reader",
			send_welcome_email=0,
			new_password=password,
			roles=[{"role": "HR User"}],
		).insert()
		timestamp = now_datetime()
		common = ["creation", "modified", "owner", "modified_by"]
		audit = (timestamp, timestamp, "Administrator", "Administrator")
		company = "O31 Shell Company"
		leave_type = "O31 Shell Leave"
		# Insert synthetic rows without invoking leave notifications or workflows.
		frappe.db.bulk_insert(
			"Company",
			[*common, "name", "company_name", "abbr", "default_currency"],
			[(*audit, company, company, "O31S", "USD")],
		)
		frappe.db.bulk_insert(
			"Leave Type", [*common, "name", "leave_type_name"], [(*audit, leave_type, leave_type)]
		)
		employees = []
		leave = []
		for index in range(EMPLOYEES):
			employee = f"O31-SHELL-EMP-{index:03d}"
			display_name = f"O31 Employee {index:03d}"
			employees.append((*audit, employee, display_name, display_name, company, "Active"))
			for offset in range(LEAVE_PER_EMPLOYEE):
				day = f"2026-01-{offset + 1:02d}"
				leave.append(
					(
						*audit,
						f"{employee}-LV-{offset:02d}",
						employee,
						display_name,
						company,
						leave_type,
						day,
						day,
						1,
						"Open",
					)
				)
		frappe.db.bulk_insert(
			"Employee", [*common, "name", "first_name", "employee_name", "company", "status"], employees
		)
		frappe.db.bulk_insert(
			"Leave Application",
			[
				*common,
				"name",
				"employee",
				"employee_name",
				"company",
				"leave_type",
				"from_date",
				"to_date",
				"total_leave_days",
				"status",
			],
			leave,
		)
		if (frappe.db.count("Employee"), frappe.db.count("Leave Application")) != (
			EMPLOYEES,
			EMPLOYEES * LEAVE_PER_EMPLOYEE,
		):
			frappe.db.rollback()
			raise RuntimeError("The benchmark dataset has unexpected row counts.")
		frappe.db.commit()
		return password


@contextmanager
def benchmark_server():
	from frappe.app import application
	from werkzeug.serving import make_server

	def timed_application(environ, start_response):
		started = perf_counter_ns()

		def timed_response(status, headers, exc_info=None):
			return start_response(
				status, [*headers, (TIMING_HEADER, str(perf_counter_ns() - started))], exc_info
			)

		return application(environ, timed_response)

	server = make_server("127.0.0.1", 0, timed_application)
	worker = Thread(target=server.serve_forever, daemon=True)
	worker.start()
	try:
		yield server.server_port
	finally:
		server.shutdown()
		worker.join()
		server.server_close()


def request(port, path, *, sid=None, form=None):
	headers = {"Host": SITE, "Accept": "application/json"}
	method = "GET"
	body = None
	if form is not None:
		headers["Content-Type"] = "application/x-www-form-urlencoded"
		method = "POST"
		body = urlencode(form)
	if sid is not None:
		headers["Cookie"] = f"sid={sid}"
	with closing(HTTPConnection("127.0.0.1", port, timeout=30)) as connection:
		connection.request(method, path, body=body, headers=headers)
		response = connection.getresponse()
		payload = response.read()
		if response.status != 200:
			raise RuntimeError(f"{path} returned HTTP {response.status}.")
		return response.headers, json.loads(payload)


def clear_caches():
	from frappe.config import clear_site_config_cache

	with test_database() as frappe:
		frappe.clear_cache()
		clear_site_config_cache()


def measure(port, password):
	headers, _unused_payload = request(port, "/api/method/login", form={"usr": ACCOUNT, "pwd": password})
	cookies = SimpleCookie()
	for value in headers.get_all("Set-Cookie", []):
		cookies.load(value)
	sid = cookies["sid"].value
	rows = []
	for endpoint, path, identity_key, identity_name in ENDPOINTS:
		request(port, path, sid=sid)
		for mode in ("Önbellekli", "Önbelleksiz"):
			samples = []
			for sample_index in range(SAMPLES):
				if mode == "Önbelleksiz":
					clear_caches()
				headers, payload = request(port, path, sid=sid)
				message = payload["message"]
				if message.get("truncated") or message[identity_key]["name"] != identity_name:
					raise RuntimeError(f"{path} returned an unexpected payload at sample {sample_index + 1}.")
				samples.append(int(headers[TIMING_HEADER]) / 1e6)
			rows.append((endpoint, mode, samples))
	return rows


def report(rows):
	import erpnext
	import frappe
	import hrms

	summary = [
		"### O-31 kabuk ölçümü",
		"",
		f"Frappe {frappe.__version__}, ERPNext {erpnext.__version__}, HRMS {hrms.__version__}.",
		f"Örnek veri {EMPLOYEES} çal\u0131şan ve {EMPLOYEES * LEAVE_PER_EMPLOYEE:,} izin kayd\u0131.".replace(
			",", "."
		),
		"İstekler yerel HTTP üzerinden s\u0131rayla gitti. Hesapta HR User rolü vard\u0131.",
		"Sunucu süresi isteğin al\u0131nmas\u0131ndan yan\u0131t başl\u0131klar\u0131n\u0131n haz\u0131r olmas\u0131na kadar ölçüldü.",
		"Önbelleksiz koşudan önce her istek için Frappe site ve işlem önbelleği temizlendi.",
		"Veritaban\u0131 ve işletim sistemi önbellekleri bu ölçümde temizlenmedi.",
		"",
		"| Uç | Durum | İstek | p50 (ms) | p95 (ms) | S\u0131n\u0131r (ms) | Sonuç |",
		"| --- | --- | ---: | ---: | ---: | ---: | --- |",
	]
	passed = True
	for endpoint, mode, samples in rows:
		p95, within_budget = summarize(samples)
		passed &= within_budget
		outcome = "pass" if within_budget else "fail"
		summary.append(
			f"| {endpoint} | {mode} | {len(samples)} | {median(samples):.3f} | {p95:.3f} | {LIMIT_MS} | {outcome} |"
		)
	return "\n".join(summary), passed


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--status-file", type=Path, required=True)
	args = parser.parse_args()
	destination = args.status_file.resolve()
	logging.getLogger("werkzeug").setLevel(logging.WARNING)
	os.chdir("sites")
	password = seed_site()
	with benchmark_server() as port:
		rows = measure(port, password)
	summary, passed = report(rows)
	with destination.open("a", encoding="utf-8") as output:
		output.write(f"\n\n{summary}\n")
	print(summary)
	return 0 if passed else 1


if __name__ == "__main__":
	raise SystemExit(main())
