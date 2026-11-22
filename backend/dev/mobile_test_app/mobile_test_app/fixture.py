"""Synthetic identities and records for a disposable mobile sync test site."""

import json
import time

import frappe
from platform_core.mobil.protocol import (
	UUID_PATTERN,
	Command,
	content_digest,
	scoped_record_key,
	unavailable_record,
	uuid4_id,
)

from .load_accounts import LOAD_ACCOUNTS

SITE = "test-mobile.localhost"
FIRST = "mobile-first@example.test"
SECOND = "mobile-second@example.test"
RATE = "mobile-rate@example.test"
REVOKE = "mobile-revoke@example.test"
REVOKE_ONE = "mobile-revoke-one@example.test"
RECORD = "Mobile Fixture Record"
MOBILE_PATHS = frozenset(
	f"/api/method/platform_core.api.mobile.v1_{action}"
	for action in (
		"register",
		"revoke",
		"pull",
		"push",
		"cleanup",
		"activity",
		"list_installations",
		"revoke_installation",
	)
)
PROBE_PATH = "/api/method/mobile_test_app.fixture.commit_probe"
TOKENS = {
	**LOAD_ACCOUNTS,
	"Bearer fixture-first": FIRST,
	"Bearer fixture-second": SECOND,
	"Bearer fixture-rate": RATE,
	"Bearer fixture-revoke": REVOKE,
	"Bearer fixture-revoke-one": REVOKE_ONE,
}
WRITER_HOLD_SECONDS = 6


def _require_test_site():
	if frappe.local.site != SITE or not frappe.conf.get("allow_tests"):
		raise RuntimeError("Mobile HTTP fixture requires the isolated mobile test site")


def setup():
	_require_test_site()
	for user, name in (
		(FIRST, "First Test"),
		(SECOND, "Second Test"),
		(RATE, "Rate Test"),
		(REVOKE, "Revocation Test"),
		(REVOKE_ONE, "Single Revocation Test"),
		*((account, "Load Test") for account in LOAD_ACCOUNTS.values()),
	):
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": name,
					"user_type": "System User",
					"send_welcome_email": 0,
				}
			).insert()
	if not frappe.db.exists("DocType", RECORD):
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": RECORD,
				"module": "Mobile Test App",
				"custom": 1,
				"autoname": "hash",
				"fields": [
					{"fieldname": "record_id", "fieldtype": "Data", "label": "Record", "unique": 1},
					{"fieldname": "title", "fieldtype": "Data", "label": "Title"},
					{"fieldname": "scope_key", "fieldtype": "Data", "label": "Scope Key", "unique": 1},
				],
				"permissions": [
					{"role": "All", "if_owner": 1, "read": 1, "write": 1, "create": 1, "delete": 1}
				],
			}
		).insert()


def _signal_key(record_id, state):
	return f"mobile-fixture:{uuid4_id(record_id)}:{state}"


def _signal(record_id, state):
	frappe.cache.set_value(_signal_key(record_id, state), True, expires_in_sec=WRITER_HOLD_SECONDS * 2)


def _observed(record_id, state):
	return bool(frappe.cache.get_value(_signal_key(record_id, state), use_local_cache=False))


def _hold_commit(record_id):
	_signal(record_id, "pending")
	deadline = time.monotonic() + WRITER_HOLD_SECONDS
	while time.monotonic() < deadline:
		if _observed(record_id, "released"):
			return
		time.sleep(0.02)
	# Let Frappe finish the transaction after a broken test loses the release signal.


def authenticate():
	_require_test_site()
	request = frappe.local.request
	if frappe.session.user != "Guest" or any(request.args.getlist("cmd")) or frappe.form_dict.get("cmd"):
		return
	header = request.headers.get("Authorization")
	if request.path == PROBE_PATH and header == "Bearer fixture-control":
		frappe.set_user(FIRST)
		return
	if request.path == "/api/method/platform_core.api.mobile.revoke_user_installations" and header in (
		"Bearer fixture-service",
		"Bearer fixture-service-other",
	):
		frappe.set_user("Administrator")
		frappe.local.kimlik_service_claims = {
			"iss": "fixture",
			"azp": "identity-sync" if header == "Bearer fixture-service" else "different-service",
		}
		return
	if request.path not in MOBILE_PATHS:
		return
	account = TOKENS.get(header)
	if not account:
		return

	try:
		body = json.loads(request.get_data(cache=True))
	except (ValueError, UnicodeError):
		body = None
	installation = request.headers.get("X-Mobile-Test-Installation")
	if installation is None and isinstance(body, dict):
		installation = body.get("installation_id")
	if not isinstance(installation, str) or not UUID_PATTERN.fullmatch(installation):
		installation = "12345678-1234-4234-8234-123456789abc"

	issued_at = int(request.headers.get("X-Mobile-Test-Iat", time.time()))
	frappe.set_user(account)
	frappe.local.mobile_identity = {
		"site": SITE,
		"account": account,
		"scope": "mobile",
		"installation": installation,
		"issuer": "fixture",
		"subject": account,
		"iat": issued_at,
		"auth_time": int(request.headers.get("X-Mobile-Test-Auth-Time", issued_at)),
		"sid": request.headers.get("X-Mobile-Test-Sid") or content_digest(["fixture-session", account]),
	}
	mismatch = request.headers.get("X-Mobile-Test-Identity-Mismatch")
	if mismatch in {"site", "scope", "account"}:
		frappe.local.mobile_identity[mismatch] = "invalid-fixture-value"

	frappe.local.mobile_commands = {
		f"fixture.{action}": FixtureCommand(action)
		for action in ("create", "create_bad_scope", "update", "delete", "transfer")
	}
	frappe.local.mobile_projections = {"fixture": projection}
	frappe.local.mobile_inventories = {"fixture": scan_inventory}
	writer = request.headers.get("X-Mobile-Test-Writer")
	if writer:
		_signal(writer, "entered")


@frappe.whitelist(methods=["POST"])
def commit_probe():
	_require_test_site()
	request = frappe.local.request
	if request.path != PROBE_PATH or request.headers.get("Authorization") != "Bearer fixture-control":
		frappe.throw("Fixture control token required", frappe.PermissionError)
	if not frappe.has_permission("User", "read", FIRST):
		frappe.throw("Fixture control permission required", frappe.PermissionError)
	body = request.get_json()
	record_id = uuid4_id(body["record_id"])
	if body.get("release") is True:
		_signal(record_id, "released")
	return {state: _observed(record_id, state) for state in ("pending", "entered")}


def _scope_key(account, record_id):
	return scoped_record_key("fixture", content_digest(["fixture", account]), record_id)


def _record(account, record_id, *, lock=False):
	filters = {"record_id": record_id, "scope_key": _scope_key(account, record_id)}
	name = frappe.db.get_value(RECORD, filters, "name", for_update=lock)
	return frappe.get_doc(RECORD, name, for_update=lock) if name is not None else None


def scan_inventory(account, after, limit):
	filters = {"owner": account}
	if after is not None:
		filters["record_id"] = [">", after]
	return frappe.get_list(RECORD, filters=filters, order_by="record_id asc", limit=limit, pluck="record_id")


def projection(account, record_id):
	doc = _record(account, record_id)
	if doc is None or not frappe.has_permission(RECORD, "read", doc=doc, user=account):
		return None
	return {"version": str(doc.modified), "fields": {"title": doc.title}}


class FixtureCommand:
	record_type = "fixture"

	def __init__(self, action):
		self.action = action
		operation = {"transfer": "update", "create_bad_scope": "create"}.get(action, action)
		self.declaration = Command(operation, frozenset({"title"}))

	def authorize(self, account, record_id):
		if self.declaration.action == "create":
			if frappe.db.get_value(RECORD, {"record_id": record_id}, "name"):
				raise unavailable_record()
			allowed = frappe.has_permission(RECORD, "create", user=account)
		else:
			doc = _record(account, record_id, lock=True)
			permission = "delete" if self.action == "delete" else "write"
			allowed = doc is not None and frappe.has_permission(RECORD, permission, doc=doc, user=account)
		if not allowed:
			raise unavailable_record()

	def read_locked(self, account, record_id):
		current = projection(account, record_id)
		if current is None:
			return None
		return {"kind": "upsert", "record_type": self.record_type, "record_id": record_id, **current}

	def apply(self, account, record_id, fields):
		if fields.get("title") == "Delayed fixture":
			# The callback runs after the command, change event and operation log have been written.
			frappe.db.before_commit.add(lambda: _hold_commit(record_id))
		if self.declaration.action == "create":
			scope_account = SECOND if self.action == "create_bad_scope" else account
			key = _scope_key(scope_account, record_id)
			try:
				frappe.get_doc(
					{"doctype": RECORD, "record_id": record_id, "scope_key": key, **fields}
				).insert()
			except (frappe.DuplicateEntryError, frappe.UniqueValidationError) as error:
				raise unavailable_record() from error
			return

		doc = _record(account, record_id, lock=True)
		if self.action == "delete":
			doc.delete()
		elif self.action == "transfer":
			recipient = SECOND if account == FIRST else FIRST
			frappe.db.set_value(
				RECORD, doc.name, {"owner": recipient, "scope_key": _scope_key(recipient, record_id)}
			)
		else:
			doc.update(fields)
			doc.save()
