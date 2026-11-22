"""Hand-started performance measurement of the access rule engine (O-31).

Limits: p95 of the server time is at most 500 ms on a read endpoint and at most 1 second on a
write endpoint. Sample data: 200 employees and 2,000 records. Every endpoint is called at least
50 times.

Start it by hand on a development or test site with `bench --site <site> execute`, followed by
the dotted path of this module and `.measure`. `COMMAND` below holds the full line.

It refuses to run unless the site has `allow_tests` set, because it writes made-up employees,
records and rules. There is no HTTP endpoint for it for the same reason.

It works on a document type of its own (`MEASURE_DOCTYPE`), made the first time it runs.
Records, rules and permission rows of every other type stay as they were. It keeps the names
of the employees and rules it creates and deletes only those, also when it stops half way.
Every record of the run carries the run's mark in its title, also a record made by a request,
so a run that stops early still finds them. The made-up roles, users and company of the test
fixtures are created when missing and stay on the site.

The requests go through the WSGI application of Frappe, like the tests do (D-6). The time is the
whole request in this process: session, permission hooks, query and response. Network time is
not part of it. All people and records are made up.
"""

import json
import statistics
import time

import frappe
from frappe.permissions import reset_perms
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client, now

from platform_core.erisim import rules
from platform_core.erisim.tests import base

# Built from the module name, so it stays right when the package is renamed.
COMMAND = f"bench --site <site> execute {__name__}.measure"
READ_LIMIT_MS = 500
WRITE_LIMIT_MS = 1000
EMPLOYEES = 200
RECORDS = 2000
MARK = "ER Perf"
LIST_FIELDS = ["name", "title", "employee", "status"]
METHOD = "/api/method/"
# The type the measurement writes to. Nothing else uses it, so its records and its permission
# rows belong to the measurement alone.
MEASURE_DOCTYPE = "AR Measurement Request"
RESOURCE = base.REST + MEASURE_DOCTYPE


def p95(samples: list[float]) -> float:
	return statistics.quantiles(samples, n=20, method="inclusive")[-1]


def send(client, method: str, path: str, *, body=None, query=None):
	headers = {"Accept": "application/json"}
	kwargs = {"path": path, "method": method, "headers": headers}
	if body is not None:
		headers["Content-Type"] = "application/json"
		kwargs["data"] = json.dumps(body)
	if query:
		kwargs["query_string"] = query
	return make_request(client.open, args=(), kwargs=kwargs, site=frappe.local.site)


def login(user: str):
	client = get_test_client(use_cookies=True)
	response = send(client, "POST", METHOD + "login", body={"usr": user, "pwd": base.PASSWORD})
	if response.status_code != 200:
		raise RuntimeError(f"Login failed for {user}: {response.status_code}")
	return client


def new_sample() -> dict:
	"""The names of everything this run creates. `clean` deletes these and nothing else."""
	return {"employees": [], "rules": [], "run": frappe.generate_hash(length=6)}


def seed(sample: dict, employees: int, records: int) -> None:
	"""Create the sample: employees in a tree, records spread over them, and the rules."""
	base.ensure_fixtures()
	if not frappe.db.exists("DocType", MEASURE_DOCTYPE):
		frappe.get_doc(base.request_doctype(MEASURE_DOCTYPE)).insert()
	people = {email: base.employee_of(email) for email in base.RECORD_OWNERS}
	managers = [people[base.MANAGER_1], people[base.MANAGER_2]]
	run = sample["run"]
	for index in range(max(employees - len(people), 0)):
		# The first seven have no manager and lead a team each. The others are spread over all nine.
		reports_to = None if index < 7 else managers[index % len(managers)]
		doc = frappe.get_doc(
			doctype="Employee",
			first_name=f"{MARK} {run} {index:03d}",
			company=base.COMPANY,
			status="Active",
			gender=base.GENDER,
			date_of_birth="1990-01-01",
			date_of_joining="2020-01-01",
			create_user_permission=0,
			reports_to=reports_to,
		).insert()
		sample["employees"].append(doc.name)
		if index < 7:
			managers.append(doc.name)
	owners = [*people.values(), *sample["employees"]]
	stamp = now()
	fields = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx"]
	fields += ["title", "employee", "company", "status", "salary_amount"]
	rows = [
		(
			frappe.generate_hash(length=10),
			stamp,
			stamp,
			"Administrator",
			"Administrator",
			0,
			0,
			f"{MARK} {run} {number:04d}",
			owners[number % len(owners)],
			base.COMPANY,
			"Open",
			1234,
		)
		for number in range(records)
	]
	sample["records"] = len(rows)
	frappe.db.bulk_insert(MEASURE_DOCTYPE, fields, rows)
	for rule in base.ErisimTestCase.RULES:
		doc = frappe.get_doc(
			{"doctype": base.RULE_DOCTYPE, "document_type": MEASURE_DOCTYPE, "is_active": 1, **rule}
		)
		sample["rules"].append(doc.insert().name)
	# Committed on purpose: the requests use another connection.
	frappe.db.commit()  # nosemgrep: frappe-request-commit
	sample["total_employees"] = len(owners)
	sample["own"] = {
		email: next(row[0] for row in rows if row[8] == employee) for email, employee in people.items()
	}


def clean(sample: dict) -> None:
	"""Delete what this run created. Nothing of any other type or run is touched."""
	frappe.set_user("Administrator")
	frappe.db.rollback()
	if frappe.db.exists("DocType", MEASURE_DOCTYPE):
		# By the run's mark, so a record that a request created is removed as well.
		frappe.db.delete(MEASURE_DOCTYPE, {"title": ("like", f"{MARK} {sample['run']}%")})
		# The level access case writes permission rows of this type. The type is the measurement's own.
		reset_perms(MEASURE_DOCTYPE)
		frappe.clear_cache(doctype=MEASURE_DOCTYPE)
	for name in sample["rules"]:
		if frappe.db.exists(base.RULE_DOCTYPE, name):
			frappe.delete_doc(base.RULE_DOCTYPE, name, force=True)
	# Team members were created after their managers, so the reverse order deletes them first.
	for name in reversed(sample["employees"]):
		if frappe.db.exists("Employee", name):
			frappe.delete_doc("Employee", name, force=True)
	# Committed on purpose: the sample must be gone for every connection.
	frappe.db.commit()  # nosemgrep: frappe-request-commit


def timed(calls: int, request) -> tuple[list[float], set[int]]:
	samples, statuses = [], set()
	for number in range(calls):
		started = time.perf_counter()
		response = request(number)
		samples.append((time.perf_counter() - started) * 1000)
		statuses.add(response.status_code)
	return samples, statuses


def endpoint_cases(sample: dict) -> list[tuple]:
	"""Each case: kind, label, user and a function that sends request number `n`."""
	employee, manager, hr, admin = (
		login(user) for user in (base.EMPLOYEE_1, base.MANAGER_1, base.HR, base.ADMIN)
	)
	own = sample["own"][base.EMPLOYEE_1]
	listing = {"fields": json.dumps(LIST_FIELDS), "limit": 20}
	view = {"doctype": MEASURE_DOCTYPE, "fields": json.dumps(LIST_FIELDS), "page_length": 20, "start": 0}
	search = {"doctype": MEASURE_DOCTYPE, "txt": MARK, "page_length": 10}
	access = METHOD + "platform_core.api.access."
	created: list[str] = []

	def create(_number):
		body = {"title": f"{MARK} {sample['run']} created", "employee": employee_name}
		response = send(employee, "POST", RESOURCE, body=body)
		if response.status_code == 200:
			created.append(response.json["data"]["name"])
		return response

	def delete(_number):
		# The create case ran first and left one record for the warm-up and one for each call.
		return send(hr, "DELETE", f"{RESOURCE}/{created.pop()}")

	employee_name = base.employee_of(base.EMPLOYEE_1)
	rule = sample["rules"][0]
	rule_path = f"{base.REST}{base.RULE_DOCTYPE}/{rule}"
	level = {"doctype": MEASURE_DOCTYPE, "role": base.ROLE_MANAGER, "permlevel": 1, "write": False}
	return [
		("read", "List, own scope", lambda n: send(employee, "GET", RESOURCE, query=listing)),
		("read", "List, team scope", lambda n: send(manager, "GET", RESOURCE, query=listing)),
		("read", "List, all scope", lambda n: send(hr, "GET", RESOURCE, query=listing)),
		("read", "Single record", lambda n: send(employee, "GET", f"{RESOURCE}/{own}")),
		(
			"read",
			"Count, team scope",
			lambda n: send(
				manager,
				"POST",
				METHOD + "frappe.desk.reportview.get_count",
				body={"doctype": MEASURE_DOCTYPE},
			),
		),
		(
			"read",
			"Report view, team scope",
			lambda n: send(manager, "POST", METHOD + "frappe.desk.reportview.get", body=view),
		),
		(
			"read",
			"Link search, team scope",
			lambda n: send(manager, "POST", METHOD + "frappe.desk.search.search_link", body=search),
		),
		(
			"read",
			"Link validation",
			lambda n: send(
				employee,
				"POST",
				METHOD + "frappe.client.validate_link_and_fetch",
				body={"doctype": MEASURE_DOCTYPE, "docname": own},
			),
		),
		(
			"read",
			"Explain permission",
			lambda n: send(
				employee,
				"GET",
				access + "explain_permission",
				query={"doctype": MEASURE_DOCTYPE, "name": own},
			),
		),
		(
			"read",
			"Access summary",
			lambda n: send(manager, "GET", access + "get_access_summary", query={"doctype": MEASURE_DOCTYPE}),
		),
		("write", "Create record", create),
		(
			"write",
			"Update record",
			lambda n: send(
				employee, "PUT", f"{RESOURCE}/{own}", body={"title": f"{MARK} {sample['run']} edit {n}"}
			),
		),
		("write", "Delete record", delete),
		(
			"write",
			"Change Access Rule",
			lambda n: send(admin, "PUT", rule_path, body={"description": f"Measurement {n}"}),
		),
		(
			"write",
			"Set level access",
			lambda n: send(admin, "POST", access + "set_level_access", body={**level, "read": not n % 2}),
		),
	]


def measure_endpoints(sample: dict, calls: int) -> list[dict]:
	results = []
	for kind, label, request in endpoint_cases(sample):
		request(0)  # warm-up: the first call fills the metadata caches
		samples, statuses = timed(calls, request)
		limit = READ_LIMIT_MS if kind == "read" else WRITE_LIMIT_MS
		value = p95(samples)
		results.append(
			{
				"kind": kind,
				"endpoint": label,
				"calls": len(samples),
				"statuses": sorted(statuses),
				"median_ms": round(statistics.median(samples), 1),
				"p95_ms": round(value, 1),
				"limit_ms": limit,
				# A delete answers 202. Any other answer outside 2xx means the case did not really run.
				"result": "pass"
				if value <= limit and all(200 <= status < 300 for status in statuses)
				else "fail",
			}
		)
	return results


def list_times(user: str, calls: int, page: int) -> list[float]:
	frappe.set_user(user)
	samples = []
	for _number in range(calls + 1):
		# A new request starts with no rules read. Without this the first loop would pay for all.
		frappe.local.request_cache.clear()
		started = time.perf_counter()
		frappe.get_list(MEASURE_DOCTYPE, fields=LIST_FIELDS, limit=page)
		samples.append((time.perf_counter() - started) * 1000)
	frappe.set_user("Administrator")
	return samples[1:]


def set_rules_active(names: list[str], active: int) -> None:
	for name in names:
		# Measurement switch only. `set_value` keeps the rule's own validation out of the timing.
		frappe.db.set_value(base.RULE_DOCTYPE, name, "is_active", active)
	# Committed on purpose: the next timing must not wait on this change.
	frappe.db.commit()  # nosemgrep: frappe-request-commit
	rules.clear_cache()


def measure_rule_cost(sample: dict, calls: int) -> list[dict]:
	"""Time the same list read with the rules active and with the rules switched off.

	Only the rules of this run are switched. A site that has other active rules on the test
	type keeps them, and the "without rules" column then still includes their cost.
	"""
	results = []
	# The requests above changed a rule on another connection. Start from a fresh snapshot.
	frappe.db.rollback()
	scopes = (("own", base.EMPLOYEE_1), ("team", base.MANAGER_1), ("all", base.HR))
	for page in (20, 500):
		for scope, user in scopes:
			set_rules_active(sample["rules"], 1)
			with_rules = list_times(user, calls, page)
			set_rules_active(sample["rules"], 0)
			without_rules = list_times(user, calls, page)
			results.append(
				{
					"scope": scope,
					"page": page,
					"calls": calls,
					"with_rules_median_ms": round(statistics.median(with_rules), 2),
					"without_rules_median_ms": round(statistics.median(without_rules), 2),
					"added_median_ms": round(
						statistics.median(with_rules) - statistics.median(without_rules), 2
					),
					"with_rules_p95_ms": round(p95(with_rules), 2),
					"without_rules_p95_ms": round(p95(without_rules), 2),
				}
			)
	set_rules_active(sample["rules"], 1)
	return results


def as_markdown(report: dict) -> str:
	lines = [
		f"Sample: {report['employees']} employees, {report['records']} records, {report['calls']} calls each.",
		"",
		"| Kind | Endpoint | Calls | Median ms | p95 ms | Limit ms | Result |",
		"| --- | --- | --- | --- | --- | --- | --- |",
	]
	lines += [
		f"| {row['kind']} | {row['endpoint']} | {row['calls']} | {row['median_ms']} | {row['p95_ms']} "
		f"| {row['limit_ms']} | {row['result']} |"
		for row in report["endpoints"]
	]
	lines += [
		"",
		"| Scope | Page | With rules, median ms | Without rules, median ms | Added ms | With rules, p95 ms |",
		"| --- | --- | --- | --- | --- | --- |",
	]
	lines += [
		f"| {row['scope']} | {row['page']} | {row['with_rules_median_ms']} | {row['without_rules_median_ms']} "
		f"| {row['added_median_ms']} | {row['with_rules_p95_ms']} |"
		for row in report["rule_cost"]
	]
	return "\n".join(lines)


def measure(calls: int = 50, keep: int = 0, employees: int = EMPLOYEES, records: int = RECORDS) -> dict:
	"""Seed the sample, measure every endpoint and the rule cost, print the result and clean up."""
	if not frappe.conf.allow_tests:
		raise RuntimeError("The measurement writes sample data. Run it on a site with allow_tests set.")
	calls = max(int(calls), 50)
	# A full queue slows every write and fails deletes. Start with room in it.
	base.run_queued_jobs()
	sample = new_sample()
	try:
		seed(sample, int(employees), int(records))
		report = {
			"employees": sample["total_employees"],
			"records": sample["records"],
			"calls": calls,
			"endpoints": measure_endpoints(sample, calls),
			"rule_cost": measure_rule_cost(sample, calls),
		}
	finally:
		if not int(keep):
			clean(sample)
	print(as_markdown(report))
	return report
