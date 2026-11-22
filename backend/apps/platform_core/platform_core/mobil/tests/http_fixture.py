"""Synthetic data for an isolated test site. Production hooks never import this module."""

import time

import frappe

from platform_core.mobil.protocol import Command, MobileError

SITE = "test-mobile.localhost"
FIRST = "mobile-first@example.test"
SECOND = "mobile-second@example.test"
RATE = "mobile-rate@example.test"
RECORD = "Mobile Fixture Record"


def _require_test_site():
	if frappe.local.site != SITE or not frappe.conf.get("allow_tests"):
		raise RuntimeError("Mobile HTTP fixture requires the isolated mobile test site")


def setup():
	_require_test_site()
	for user, name in ((FIRST, "First Test"), (SECOND, "Second Test"), (RATE, "Rate Test")):
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
				"module": "Mobil",
				"custom": 1,
				"autoname": "field:record_id",
				"fields": [
					{"fieldname": "record_id", "fieldtype": "Data", "label": "Record", "unique": 1},
					{"fieldname": "title", "fieldtype": "Data", "label": "Title"},
				],
				"permissions": [
					{"role": "All", "if_owner": 1, "read": 1, "write": 1, "create": 1, "delete": 1}
				],
			}
		).insert()


def authenticate():
	_require_test_site()
	request = frappe.local.request
	path = request.path
	if not path.startswith("/api/method/platform_core.api.mobile.v1_"):
		return
	if frappe.session.user != "Guest" or "cmd" in request.args or "cmd" in frappe.form_dict:
		return

	header = request.headers.get("Authorization")
	account = {
		"Bearer fixture-first": FIRST,
		"Bearer fixture-second": SECOND,
		"Bearer fixture-rate": RATE,
	}.get(header)
	if account:
		frappe.set_user(account)
		frappe.local.mobile_identity = {
			"site": SITE,
			"account": account,
			"scope": "mobile",
			"issuer": "fixture",
			"subject": account,
		}
		from platform_core.api import mobile

		mobile.COMMANDS = {
			f"fixture.{action}": FixtureCommand(action)
			for action in ("create", "update", "delete", "transfer")
		}
		mobile.PROJECTIONS = {"fixture": projection}


def _record(record_id):
	if frappe.db.get_value(RECORD, record_id, "name", for_update=True):
		return frappe.get_doc(RECORD, record_id, for_update=True)
	return None


def projection(account, record_id):
	doc = _record(record_id)
	if doc is None or not frappe.has_permission(RECORD, "read", doc=doc, user=account):
		return None
	return {"version": str(doc.modified), "fields": {"title": doc.title}}


class FixtureCommand:
	record_type = "fixture"

	def __init__(self, action):
		self.action = action
		self.declaration = Command("update" if action == "transfer" else action, frozenset({"title"}))

	def authorize(self, account, record_id):
		doc = _record(record_id)
		if self.action == "create":
			if doc is not None:
				raise MobileError("record_exists", 409)
			allowed = frappe.has_permission(RECORD, "create", user=account)
		else:
			permission = "delete" if self.action == "delete" else "write"
			allowed = doc is not None and frappe.has_permission(RECORD, permission, doc=doc, user=account)
		if not allowed:
			raise MobileError("record_forbidden", 403)

	def read_locked(self, account, record_id):
		current = projection(account, record_id)
		if current is None:
			return None
		return {"kind": "upsert", "record_type": self.record_type, "record_id": record_id, **current}

	def apply(self, account, record_id, fields):
		if fields.get("title") == "Delayed fixture":
			# Keep the HTTP write open while a second fixture request is sent.
			time.sleep(0.4)
		if self.action == "create":
			frappe.get_doc({"doctype": RECORD, "record_id": record_id, **fields}).insert()
			return

		doc = _record(record_id)
		if self.action == "delete":
			doc.delete()
		elif self.action == "transfer":
			frappe.db.set_value(RECORD, doc.name, "owner", SECOND)
		else:
			doc.update(fields)
			doc.save()
