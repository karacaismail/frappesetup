"""Authorization tests of the access endpoints. The security gate requires these two tests for each endpoint.

The detailed behavior tests are in the `platform_core/erisim/tests/` folder.
"""

import re
import secrets

import frappe

from platform_core.access.record_links import LINK, REQUEST
from platform_core.access.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	HR,
	ROLE_EMPLOYEE,
	AccessRuleTestCase,
)

FIELD_BODY = {"doctype": DOCTYPE, "fieldname": "salary_amount", "permlevel": 0}
LEVEL_BODY = {"doctype": DOCTYPE, "role": ROLE_EMPLOYEE, "permlevel": 1, "read": True, "write": True}


class TestAccessEndpoints(AccessRuleTestCase):
	def explain(self, client, name: str, **query):
		return self.api(
			client, "GET", "explain_permission", query={"doctype": DOCTYPE, "name": name, **query}
		)

	def test_explain_permission_guest_denied(self):
		response = self.explain(self.anonymous(), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 403)

	def test_explain_permission_foreign_data_denied(self):
		"""An employee cannot ask about the permission of someone else. On the record of someone else a single denial reason is returned."""
		client = self.login(EMPLOYEE_1)

		other_user = self.explain(client, self.records[EMPLOYEE_1], user=EMPLOYEE_2)
		other_record = self.explain(client, self.records[EMPLOYEE_2])
		rule_doctype = self.api(
			client, "GET", "explain_permission", query={"doctype": "PLT Access Rule", "name": "AR-00001"}
		)

		self.assertEqual(other_user.status_code, 403)
		self.assertEqual(other_record.status_code, 200)
		self.assertFalse(other_record.json["message"]["allowed"])
		self.assertEqual(other_record.json["message"]["reason"], "not_permitted_or_missing")
		self.assertEqual(other_record.json["message"]["rules"], [])
		self.assertEqual(rule_doctype.status_code, 403)

	def test_get_access_summary_guest_denied(self):
		response = self.api(self.anonymous(), "GET", "get_access_summary", query={"doctype": DOCTYPE})

		self.assertEqual(response.status_code, 403)

	def test_get_access_summary_foreign_data_denied(self):
		"""The employee has no read permission on the “Access Rule” document type."""
		response = self.api(
			self.login(EMPLOYEE_1), "GET", "get_access_summary", query={"doctype": "PLT Access Rule"}
		)

		self.assertEqual(response.status_code, 403)

	def test_set_field_level_guest_denied(self):
		response = self.api(self.anonymous(), "POST", "set_field_level", body=FIELD_BODY)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("salary_amount").permlevel, 1)

	def test_set_field_level_foreign_data_denied(self):
		response = self.api(self.login(EMPLOYEE_1), "POST", "set_field_level", body=FIELD_BODY)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("salary_amount").permlevel, 1)

	def test_set_level_access_guest_denied(self):
		response = self.api(self.anonymous(), "POST", "set_level_access", body=LEVEL_BODY)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))

	def test_set_level_access_foreign_data_denied(self):
		response = self.api(self.login(EMPLOYEE_1), "POST", "set_level_access", body=LEVEL_BODY)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))


# The record type is governed by the access rule engine. A role without a rule reads nothing,
# so the System Manager cannot share these records. HR reads every record and has the share
# permission, so HR is the sharer here.
SHARER = HR


class TestRecordLinks(AccessRuleTestCase):
	def clean_link(self, link_id):
		frappe.db.delete("Activity Log", {"reference_doctype": LINK, "reference_name": link_id})
		frappe.db.delete(LINK, {"name": link_id})
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def clean_requests(self, name):
		requests = frappe.get_all(
			REQUEST, filters={"target_type": DOCTYPE, "target_name": name}, pluck="name"
		)
		if requests:
			frappe.db.delete(
				"Activity Log", {"reference_doctype": REQUEST, "reference_name": ("in", requests)}
			)
			frappe.db.delete(REQUEST, {"name": ("in", requests)})
			frappe.db.commit()  # nosemgrep: frappe-request-commit

	def rpc(self, client, method, **body):
		return self.send(client, "POST", f"/api/method/platform_core.api.access.{method}", body=body)

	def test_private_link_uses_the_readers_own_permission(self):
		name = self.records[EMPLOYEE_2]
		sharer = self.login(SHARER)
		response = self.rpc(sharer, "create_record_link", doctype=DOCTYPE, name=name)
		self.assertEqual(response.status_code, 200)
		link = response.json["message"]
		self.addCleanup(self.clean_link, link["id"])
		token = link["path"].split("#", 1)[1]
		self.assertNotIn(name, link["path"])

		reader = self.login(EMPLOYEE_2)
		other = self.login(EMPLOYEE_1)
		opened = self.rpc(reader, "open_record_link", token=token)
		self.assertEqual(opened.status_code, 200)
		self.assertEqual(opened.json["message"]["name"], name)
		denied = self.rpc(other, "open_record_link", token=token)
		self.assertEqual(denied.status_code, 404)
		self.assertNotIn(name, denied.get_data(as_text=True))

		self.assertEqual(self.rpc(other, "revoke_record_link", link_id=link["id"]).status_code, 404)
		self.assertEqual(self.rpc(sharer, "revoke_record_link", link_id=link["id"]).status_code, 200)
		self.assertEqual(self.rpc(sharer, "revoke_record_link", link_id=link["id"]).status_code, 200)
		self.assertEqual(self.rpc(reader, "open_record_link", token=token).status_code, 410)
		for event in ("Record link created", "Record link revoked"):
			self.assertEqual(
				frappe.db.count("Activity Log", {"reference_name": link["id"], "subject": event}), 1
			)

	def test_request_record_access_foreign_data_denied(self):
		name = self.records[EMPLOYEE_2]
		self.addCleanup(self.clean_requests, name)
		reader = self.login(EMPLOYEE_1)
		valid = self.rpc(reader, "request_record_access", doctype=DOCTYPE, name=name)
		missing = self.rpc(reader, "request_record_access", doctype=DOCTYPE, name="missing-record")
		repeat = self.rpc(reader, "request_record_access", doctype=DOCTYPE, name=name)

		self.assertEqual(valid.status_code, 202)
		self.assertEqual(valid.json, {"message": {"status": "received"}})
		self.assertEqual(valid.json, missing.json)
		self.assertEqual(valid.json, repeat.json)
		filters = {"target_type": DOCTYPE, "target_name": name, "owner": EMPLOYEE_1}
		self.assertEqual(frappe.db.count(REQUEST, filters), 1)
		request_id = frappe.db.get_value(REQUEST, filters, "name")
		self.assertTrue(
			frappe.db.exists(
				"Activity Log", {"reference_name": request_id, "subject": "Record access requested"}
			)
		)
		self.assertEqual(self.rest_get(reader, name).status_code, 403)

	def test_guest_preview_depends_on_route_shape_only(self):
		visitor = self.anonymous()
		name = self.records[EMPLOYEE_2]
		prefix = "/panel/hrms/leave-application/"
		existing = self.send(visitor, "GET", prefix + name)
		missing = self.send(visitor, "GET", prefix + "missing-record")
		self.assertEqual(existing.status_code, 200)
		self.assertEqual(missing.status_code, 200)
		self.assertEqual(existing.headers["X-Robots-Tag"], "noindex, nofollow")
		first = existing.get_data(as_text=True)
		second = missing.get_data(as_text=True)
		self.assertNotIn(self.stored(name, "title"), first)
		self.assertEqual(first.replace(name, "missing-record"), second)
		for prop, expected in (
			("title", "Record"),
			("description", "Sign in to open this record."),
			("image", "/api/method/platform_core.api.shell.record_preview_image"),
		):
			pattern = rf'property="og:{prop}" content="([^"]+)"'
			left = re.search(pattern, first).group(1)
			right = re.search(pattern, second).group(1)
			self.assertEqual(left, right)
			if prop == "image":
				self.assertTrue(left.endswith(expected))
			else:
				self.assertEqual(left, expected)
		self.assertEqual(existing.headers["Vary"], "Cookie, Sec-Fetch-User")
		self.assertEqual(existing.headers["Cache-Control"], "private, no-store")

		image = self.send(visitor, "GET", "/api/method/platform_core.api.shell.record_preview_image")
		self.assertEqual(image.status_code, 200)
		self.assertEqual(image.mimetype, "image/png")
		self.assertTrue(image.data.startswith(b"\x89PNG\r\n\x1a\n"))

	def test_create_record_link_guest_denied(self):
		result = self.rpc(
			self.anonymous(), "create_record_link", doctype=DOCTYPE, name=self.records[EMPLOYEE_2]
		)
		self.assertEqual(result.status_code, 403)

	def test_create_record_link_foreign_data_denied(self):
		reader = self.login(EMPLOYEE_1)
		result = self.rpc(reader, "create_record_link", doctype=DOCTYPE, name=self.records[EMPLOYEE_2])
		missing = self.rpc(reader, "create_record_link", doctype=DOCTYPE, name="missing-record")
		self.assertEqual(result.status_code, 404)
		self.assertEqual(result.json, {"message": {"status": "unavailable"}})
		self.assertEqual(result.json, missing.json)

	def test_open_record_link_guest_denied(self):
		result = self.rpc(self.anonymous(), "open_record_link", token=secrets.token_urlsafe(32))
		self.assertEqual(result.status_code, 403)

	def test_open_record_link_foreign_data_denied(self):
		sharer = self.login(SHARER)
		result = self.rpc(sharer, "create_record_link", doctype=DOCTYPE, name=self.records[EMPLOYEE_2])
		link = result.json["message"]
		self.addCleanup(self.clean_link, link["id"])
		reader = self.login(EMPLOYEE_1)
		denied = self.rpc(reader, "open_record_link", token=link["path"].split("#", 1)[1])
		missing = self.rpc(reader, "open_record_link", token=secrets.token_urlsafe(32))
		self.assertEqual(denied.status_code, 404)
		self.assertEqual(denied.json, {"message": {"status": "unavailable"}})
		self.assertEqual(denied.json, missing.json)

	def test_revoke_record_link_guest_denied(self):
		result = self.rpc(self.anonymous(), "revoke_record_link", link_id=secrets.token_hex(16))
		self.assertEqual(result.status_code, 403)

	def test_revoke_record_link_foreign_data_denied(self):
		sharer = self.login(SHARER)
		result = self.rpc(sharer, "create_record_link", doctype=DOCTYPE, name=self.records[EMPLOYEE_2])
		link_id = result.json["message"]["id"]
		self.addCleanup(self.clean_link, link_id)
		reader = self.login(EMPLOYEE_1)
		result = self.rpc(reader, "revoke_record_link", link_id=link_id)
		missing = self.rpc(reader, "revoke_record_link", link_id=secrets.token_hex(16))
		self.assertEqual(result.status_code, 404)
		self.assertEqual(result.json, {"message": {"status": "unavailable"}})
		self.assertEqual(result.json, missing.json)
		self.assertFalse(frappe.db.get_value(LINK, link_id, "revoked_at"))

	def test_request_record_access_guest_denied(self):
		result = self.rpc(
			self.anonymous(), "request_record_access", doctype=DOCTYPE, name=self.records[EMPLOYEE_2]
		)
		self.assertEqual(result.status_code, 403)
