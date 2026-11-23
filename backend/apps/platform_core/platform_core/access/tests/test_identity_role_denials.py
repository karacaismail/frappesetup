"""G-53/G-62/G-121 denial coverage through Frappe's real request dispatcher.

These tests cover existing Website User and operator boundaries. They do not claim
that the unimplemented Tenant Admin role-management API is complete.
"""

import json

import frappe

from platform_core.access.tests.base import (
	ADMIN,
	DESK_ONLY,
	DOCTYPE,
	EMPLOYEE_1,
	PORTAL,
	REST,
	ROLE_EMPLOYEE,
	AccessRuleTestCase,
)


class TestIdentityRoleDenials(AccessRuleTestCase):
	def assert_denied_without_records(self, response, *, api_version=1):
		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		if api_version == 2:
			self.assertEqual([error["type"] for error in response.json["errors"]], ["PermissionError"])
		else:
			self.assertEqual(response.json["exc_type"], "PermissionError")
		self.assertNotIn("data", response.json)
		self.assertNotIn("message", response.json)
		for name in self.records.values():
			self.assertNotIn(name, response.get_data(as_text=True))

	def test_list_denies_authenticated_user_without_doctype_permission(self):
		self.assert_denied_without_records(self.rest_list(self.login(DESK_ONLY)), api_version=2)

	def test_report_denies_authenticated_user_without_doctype_permission(self):
		response = self.send(
			self.login(DESK_ONLY),
			"POST",
			"/api/method/frappe.desk.reportview.get",
			body={"doctype": DOCTYPE, "fields": json.dumps(["name"]), "page_length": 500},
		)
		self.assert_denied_without_records(response)

	def test_export_denies_authenticated_user_without_doctype_permission(self):
		response = self.send(
			self.login(DESK_ONLY),
			"POST",
			"/api/method/frappe.desk.reportview.export_query",
			body={
				"doctype": DOCTYPE,
				"fields": json.dumps(["name"]),
				"file_format_type": "CSV",
				"title": DOCTYPE,
				"page_length": 500,
			},
		)
		self.assert_denied_without_records(response)
		self.assertNotIn("attachment", response.headers.get("Content-Disposition", ""))

	def test_portal_user_cannot_change_session_settings(self):
		before = frappe.db.get_single_value("System Settings", "session_expiry")
		response = self.send(
			self.login(PORTAL),
			"PUT",
			REST + "System Settings/System Settings",
			body={"session_expiry": "99:00"},
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.db.get_single_value("System Settings", "session_expiry"), before)

	def test_portal_user_cannot_change_operator_roles(self):
		before = frappe.get_doc("User", ADMIN).as_dict()
		response = self.send(self.login(PORTAL), "PUT", REST + f"User/{ADMIN}", body={"roles": []})
		self.assertEqual(response.status_code, 403)
		after = frappe.get_doc("User", ADMIN).as_dict()
		self.assertEqual(after["roles"], before["roles"])
		self.assertEqual(after["modified"], before["modified"])

	def test_portal_user_cannot_disable_standard_manager_role(self):
		before = frappe.get_doc("Role", "System Manager").as_dict()
		response = self.send(self.login(PORTAL), "PUT", REST + "Role/System Manager", body={"disabled": 1})
		self.assertEqual(response.status_code, 403)
		after = frappe.get_doc("Role", "System Manager").as_dict()
		self.assertEqual(after["disabled"], before["disabled"])
		self.assertEqual(after["modified"], before["modified"])

	def test_denied_level_grant_creates_no_custom_permission(self):
		before = frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, fields=["*"])
		response = self.api(
			self.login(EMPLOYEE_1),
			"POST",
			"set_level_access",
			body={"doctype": DOCTYPE, "role": ROLE_EMPLOYEE, "permlevel": 1, "read": 1, "write": 1},
		)
		self.assertEqual(response.status_code, 403)
		after = frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, fields=["*"])
		self.assertEqual(after, before)
