"""Hand-started performance measurement of the access rule engine (O-31).

Limits: p95 of the server time is at most 500 ms on a read endpoint and at most 1 second on a
write endpoint. Sample data: 200 employees and 2,000 records. Every endpoint is called at least
50 times.

Start it by hand on a development or test site with `bench --site <site> execute`, followed by
the dotted path of this module and `.measure`. `COMMAND` below holds the full line.

It follows rule O-35 of the project record:

- It runs only on a site made for measuring: the site name starts with `perf-` and ends with
  `.localhost`, and the site configuration has `allow_performance_fixture` set to 1. On any
  other site it stops before it creates anything. There is no HTTP endpoint for it.
- It stops before it creates anything when a background job is waiting. It never runs the
  queue: a waiting job belongs to other work.
- It deletes only what it created, chosen by document type and name together.

Such a site can be thrown away after the run. The jobs that the run's own requests queue stay
in the queue of that site.

Everything it works on is its own and lives for one run only: a document type, three roles,
four users, a company, the employees, the records and the rules. Their names carry the mark of
the run, so the clean-up finds them also when the run stops half way. Nothing that was on the
site before is read as sample data, changed or deleted: no user, no role, no permission row, no
user permission, no rule and no record. It does not call the shared set-up of the tests.

The requests go through the WSGI application of Frappe, like the tests do (D-6). The time is the
whole request in this process: session, permission hooks, query and response. Network time is
not part of it. All people and records are made up.
"""

import json
import re
import statistics
import time

import frappe
from frappe.tests.test_api import make_request
from frappe.utils import cint, get_test_client, now
from frappe.utils.background_jobs import get_queues
from frappe.utils.password import update_password

from platform_core.access import rules
from platform_core.access.tests import base

# Built from the module name, so it stays right when the package is renamed.
COMMAND = f"bench --site <site> execute {__name__}.measure"
READ_LIMIT_MS = 500
WRITE_LIMIT_MS = 1000
EMPLOYEES = 200
RECORDS = 2000
MARK = "AR Measure"
LIST_FIELDS = ["name", "title", "employee", "status"]
METHOD = "/api/method/"
PASSWORD = "Made-Up-Measure-6150!"
PEOPLE = ("employee", "manager", "hr", "admin")
SITE_NAME = re.compile(r"perf-[a-z0-9][a-z0-9-]*\.localhost")
SITE_FLAG = "allow_performance_fixture"


class NotAllowedHere(RuntimeError):
	"""The site is not a measuring site (O-35)."""


class QueueNotEmpty(RuntimeError):
	"""A background job is waiting. The measurement does not start and does not run it (O-35)."""


def site_name() -> str:
	return frappe.local.site


def site_allowed(name: str, conf) -> bool:
	"""Rule O-35: a `perf-*.localhost` site whose configuration switches the fixture on."""
	return bool(SITE_NAME.fullmatch(name or "")) and cint(conf.get(SITE_FLAG)) == 1


def waiting_jobs() -> int:
	return sum(queue.count for queue in get_queues())


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
	response = send(client, "POST", METHOD + "login", body={"usr": user, "pwd": PASSWORD})
	if response.status_code != 200:
		raise RuntimeError(f"Login failed for {user}: {response.status_code}")
	return client


def new_sample() -> dict:
	"""The names of everything this run will create. They all carry the mark of the run."""
	run = frappe.generate_hash(length=6).lower()
	prefix = f"{MARK} {run}"
	return {
		"run": run,
		"started": now(),
		"prefix": prefix,
		"doctype": f"{prefix} Request",
		"company": f"{prefix} Company",
		"gender": f"{prefix} Gender",
		"roles": {kind: f"{prefix} {kind.title()}" for kind in ("employee", "manager", "hr")},
		"users": {kind: f"ar.measure.{run}.{kind}@example.test" for kind in PEOPLE},
		"rules": [],
	}


def make_type_and_people(sample: dict) -> None:
	"""The run's own roles, document type, company and four users."""
	for role in sample["roles"].values():
		frappe.get_doc(doctype="Role", role_name=role, desk_access=1).insert()
	roles = (*sample["roles"].values(), "System Manager")
	level_1 = (sample["roles"]["hr"], "System Manager")
	frappe.get_doc(base.request_doctype(sample["doctype"], roles, level_1)).insert()
	frappe.get_doc(doctype="Gender", gender=sample["gender"]).insert()
	# The company row is written directly. ERPNext's company setup creates accounts and warehouses.
	company = frappe.get_doc(
		doctype="Company",
		company_name=sample["company"],
		abbr=sample["run"].upper(),
		default_currency="TRY",
		country=frappe.db.get_value("Country", {}, "name"),
	)
	company.name = sample["company"]
	company.db_insert()
	user_roles = {
		"employee": [sample["roles"]["employee"]],
		"manager": [sample["roles"]["employee"], sample["roles"]["manager"]],
		"hr": [sample["roles"]["hr"]],
		"admin": ["System Manager"],
	}
	for kind, email in sample["users"].items():
		frappe.get_doc(
			doctype="User",
			email=email,
			first_name=f"{sample['prefix']} {kind}",
			send_welcome_email=0,
			roles=[{"role": role} for role in user_roles[kind]],
		).insert()
		update_password(email, PASSWORD)


def make_employees(sample: dict, employees: int) -> list[str]:
	"""A tree: the manager user leads a team, seven more leads have teams, the rest are members."""
	names, leads = [], []
	for index in range(employees):
		user = {0: sample["users"]["manager"], 1: sample["users"]["employee"]}.get(index)
		# Number 0 and numbers 2 to 8 lead a team. Everyone else reports to one of the leads.
		reports_to = None if index == 0 or 2 <= index <= 8 else leads[index % len(leads)]
		doc = frappe.get_doc(
			doctype="Employee",
			first_name=f"{sample['prefix']} {index:03d}",
			company=sample["company"],
			status="Active",
			gender=sample["gender"],
			date_of_birth="1990-01-01",
			date_of_joining="2020-01-01",
			user_id=user,
			# ERPNext would create a User Permission for the user. The measurement times the engine alone.
			create_user_permission=0,
			reports_to=reports_to,
		).insert()
		names.append(doc.name)
		if reports_to is None:
			leads.append(doc.name)
	return names


def make_records(sample: dict, owners: list[str], records: int) -> list[tuple]:
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
			f"{sample['prefix']} {number:04d}",
			owners[number % len(owners)],
			sample["company"],
			"Open",
			1234,
		)
		for number in range(records)
	]
	frappe.db.bulk_insert(sample["doctype"], fields, rows)
	return rows


def make_rules(sample: dict) -> None:
	"""The P1 scenario of the roadmap: own records, the team, and everything for HR."""
	definitions = (
		{"role": "employee", "scope": "own", "match_field": "employee", "allow_write": 1, "allow_create": 1},
		{"role": "manager", "scope": "team", "match_field": "employee"},
		{"role": "hr", "scope": "all", "allow_write": 1, "allow_create": 1, "allow_delete": 1},
	)
	for definition in definitions:
		doc = frappe.get_doc(
			{
				"doctype": base.RULE_DOCTYPE,
				"title": f"{sample['prefix']} {definition['role']}",
				"document_type": sample["doctype"],
				"is_active": 1,
				"allow_read": 1,
				**definition,
				"role": sample["roles"][definition["role"]],
			}
		)
		sample["rules"].append(doc.insert().name)


def seed(sample: dict, employees: int, records: int) -> None:
	"""Create the sample. Every name comes from `new_sample`, so `clean` can find all of it."""
	make_type_and_people(sample)
	owners = make_employees(sample, employees)
	rows = make_records(sample, owners, records)
	make_rules(sample)
	# Committed on purpose: the requests use another connection.
	frappe.db.commit()  # nosemgrep: frappe-request-commit
	sample["employees"] = len(owners)
	sample["records"] = len(rows)
	# Employee number 1 belongs to the employee user; its first record is the "own" record.
	sample["own"] = next(row[0] for row in rows if row[8] == owners[1])
	sample["employee_name"] = owners[1]


LOG_TABLES = (
	# log table, field with the document type, field with the name
	("Deleted Document", "deleted_doctype", "deleted_name"),
	("Version", "ref_doctype", "docname"),
	("Comment", "reference_doctype", "reference_name"),
	("Activity Log", "reference_doctype", "reference_name"),
)
OWNED_LOG_TABLES = (
	"Deleted Document",
	"Version",
	"Comment",
	"Activity Log",
	"Access Log",
	"Route History",
	"Notification Settings",
)


def delete_rows(table: str, filters: dict) -> None:
	"""Find log rows with the given filters, then delete each one by its own type and name."""
	# The clean-up's own search for rows this run wrote; the filters name the run's documents.
	for name in frappe.get_all(table, filters=filters, pluck="name", limit=0):
		frappe.db.delete(table, {"name": name})


def clean_traces(sample: dict, made: list[tuple[str, str]]) -> None:
	"""Remove the log rows Frappe wrote about the run's own documents and by the run's own users.

	`made` holds every document of the run as a pair of type and name. A log row is removed only
	when both its type and its name match a pair. A record of another type with the same name
	keeps its log rows.

	Only rows written since the run started are removed: a name such as an employee number is
	given out again after a delete, so an older row can carry the same pair.
	"""
	recent = {"creation": (">=", sample["started"])}
	by_type: dict[str, list[str]] = {}
	for doctype, name in made:
		by_type.setdefault(doctype, []).append(name)
	for doctype, names in by_type.items():
		for table, type_field, name_field in LOG_TABLES:
			delete_rows(table, {**recent, type_field: doctype, name_field: ("in", names)})
		# Frappe notes a deletion in a comment that names the type and the name in its subject.
		subjects = [f"{doctype} {name}" for name in names]
		filters = {"comment_type": "Deleted", "reference_doctype": doctype, "subject": ("in", subjects)}
		delete_rows("Comment", {**recent, **filters})
	# The records of the run's own type: every name of that type belongs to the run.
	for table, type_field, _name_field in LOG_TABLES:
		delete_rows(table, {**recent, type_field: sample["doctype"]})
	# Rows written by the run's own users, for example about a permission row a request deleted.
	users = list(sample["users"].values())
	for table in OWNED_LOG_TABLES:
		delete_rows(table, {**recent, "owner": ("in", users)})
	delete_rows("Activity Log", {**recent, "user": ("in", users)})


def clean(sample: dict) -> None:
	"""Delete everything that carries the mark of this run. Nothing else is touched."""
	frappe.set_user("Administrator")
	frappe.db.rollback()
	doctype = sample["doctype"]
	# The reads below are the clean-up's own search for what this run made, by the run's names.
	for name in frappe.get_all(base.RULE_DOCTYPE, filters={"document_type": doctype}, pluck="name", limit=0):
		frappe.delete_doc(base.RULE_DOCTYPE, name, force=True, delete_permanently=True)
	members = frappe.get_all(
		"Employee", filters={"company": sample["company"]}, pluck="name", order_by="lft desc", limit=0
	)
	for name in members:
		frappe.delete_doc("Employee", name, force=True, delete_permanently=True)
	contacts: list[str] = []
	for email in sample["users"].values():
		# Frappe makes a contact for every new user and keeps it when the user is deleted.
		for contact in frappe.get_all("Contact", filters={"user": email}, pluck="name", limit=0):
			contacts.append(contact)
			frappe.delete_doc("Contact", contact, force=True, delete_permanently=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, delete_permanently=True)
	if frappe.db.exists("DocType", doctype):
		frappe.db.delete("Custom DocPerm", {"parent": doctype})
		frappe.db.delete("Property Setter", {"doc_type": doctype})
		frappe.db.delete("DocShare", {"share_doctype": doctype})
		frappe.delete_doc("DocType", doctype, force=True, delete_permanently=True)
	for role in sample["roles"].values():
		if frappe.db.exists("Role", role):
			frappe.delete_doc("Role", role, force=True, delete_permanently=True)
	made = [(base.RULE_DOCTYPE, name) for name in sample["rules"]]
	made += [("Employee", name) for name in members]
	made += [("User", email) for email in sample["users"].values()]
	# Frappe keeps one settings record for each user and deletes it with the user.
	made += [("Notification Settings", email) for email in sample["users"].values()]
	made += [("Contact", name) for name in contacts]
	made += [("Role", role) for role in sample["roles"].values()]
	made += [("DocType", doctype), ("Company", sample["company"]), ("Gender", sample["gender"])]
	clean_traces(sample, made)
	frappe.db.delete("Company", {"name": sample["company"]})
	frappe.db.delete("Gender", {"name": sample["gender"]})
	# Committed on purpose: the sample must be gone for every connection.
	frappe.db.commit()  # nosemgrep: frappe-request-commit
	# Deleting a document type leaves its table. The name is built above from the run's mark and
	# holds no input from outside, and a table name cannot be passed as a query parameter.
	frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
	frappe.clear_cache()


def timed(calls: int, request) -> tuple[list[float], set[int]]:
	samples, statuses = [], set()
	for number in range(calls):
		started = time.perf_counter()
		response = request(number)
		samples.append((time.perf_counter() - started) * 1000)
		statuses.add(response.status_code)
	return samples, statuses


def endpoint_cases(sample: dict) -> list[tuple]:
	"""Each case: kind, label and a function that sends request number `n`."""
	employee, manager, hr, admin = (login(sample["users"][kind]) for kind in PEOPLE)
	doctype, own, prefix = sample["doctype"], sample["own"], sample["prefix"]
	resource = base.REST + doctype
	listing = {"fields": json.dumps(LIST_FIELDS), "limit": 20}
	view = {"doctype": doctype, "fields": json.dumps(LIST_FIELDS), "page_length": 20, "start": 0}
	search = {"doctype": doctype, "txt": MARK, "page_length": 10}
	access = METHOD + "platform_core.api.access."
	created: list[str] = []

	def create(_number):
		body = {"title": f"{prefix} created", "employee": sample["employee_name"]}
		response = send(employee, "POST", resource, body=body)
		if response.status_code == 200:
			created.append(response.json["data"]["name"])
		return response

	def delete(_number):
		# The create case ran first and left one record for the warm-up and one for each call.
		return send(hr, "DELETE", f"{resource}/{created.pop()}")

	rule_path = f"{base.REST}{base.RULE_DOCTYPE}/{sample['rules'][0]}"
	level = {"doctype": doctype, "role": sample["roles"]["manager"], "permlevel": 1, "write": False}
	return [
		("read", "List, own scope", lambda n: send(employee, "GET", resource, query=listing)),
		("read", "List, team scope", lambda n: send(manager, "GET", resource, query=listing)),
		("read", "List, all scope", lambda n: send(hr, "GET", resource, query=listing)),
		("read", "Single record", lambda n: send(employee, "GET", f"{resource}/{own}")),
		(
			"read",
			"Count, team scope",
			lambda n: send(
				manager, "POST", METHOD + "frappe.desk.reportview.get_count", body={"doctype": doctype}
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
				body={"doctype": doctype, "docname": own},
			),
		),
		(
			"read",
			"Explain permission",
			lambda n: send(
				employee, "GET", access + "explain_permission", query={"doctype": doctype, "name": own}
			),
		),
		(
			"read",
			"Access summary",
			lambda n: send(manager, "GET", access + "get_access_summary", query={"doctype": doctype}),
		),
		("write", "Create record", create),
		(
			"write",
			"Update record",
			lambda n: send(employee, "PUT", f"{resource}/{own}", body={"title": f"{prefix} edit {n}"}),
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


def list_times(doctype: str, user: str, calls: int, page: int) -> list[float]:
	frappe.set_user(user)
	samples = []
	for _number in range(calls + 1):
		# A new request starts with no rules read. Without this the first loop would pay for all.
		if getattr(frappe.local, "request_cache", None) is not None:
			frappe.local.request_cache.clear()
		started = time.perf_counter()
		frappe.get_list(doctype, fields=LIST_FIELDS, limit=page)
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
	"""Time the same list read with the rules active and with the rules switched off."""
	results = []
	# The requests above changed a rule on another connection. Start from a fresh snapshot.
	frappe.db.rollback()
	users = sample["users"]
	scopes = (("own", users["employee"]), ("team", users["manager"]), ("all", users["hr"]))
	for page in (20, 500):
		for scope, user in scopes:
			set_rules_active(sample["rules"], 1)
			with_rules = list_times(sample["doctype"], user, calls, page)
			set_rules_active(sample["rules"], 0)
			without_rules = list_times(sample["doctype"], user, calls, page)
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
	if not site_allowed(site_name(), frappe.conf):
		raise NotAllowedHere(
			f"The measurement runs only on a perf-*.localhost site with {SITE_FLAG} set to 1 (O-35)."
		)
	waiting = waiting_jobs()
	if waiting:
		raise QueueNotEmpty(f"{waiting} background job(s) are waiting. Nothing was created (O-35).")
	calls = max(int(calls), 50)
	sample = new_sample()
	try:
		seed(sample, int(employees), int(records))
		report = {
			"employees": sample["employees"],
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
