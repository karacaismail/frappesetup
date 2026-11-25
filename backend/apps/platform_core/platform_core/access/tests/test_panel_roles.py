"""G-168: the tenant admin assistant role, its Role Profile and its refusals.

The requests go through Frappe's WSGI application, so the session and the permission checks run
on the real path. Every person and record here is made up.

The "Tenant Admin" and "Tenant Admin Assistant" roles and their Role Profiles come from the
fixtures (AJA-832). The test does not create them.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password

from platform_core.access import panel_roles

PASSWORD = "Sahte-Parola-1680-pr!"
GRANT = "/api/method/platform_core.api.access.grant_tenant_admin_assistant"
REST = "/api/v2/document/"

ROLE_MEMBER = "PR Panel Uye"
ROLE_DESK = "PR Masa"
# A profile that would make its holder an admin. The holder must not be able to pick it.
ADMIN_PROFILE = "PR Yonetici Profil"

TENANT_ADMIN = "pr.kiraci.yonetici@example.test"
SYSTEM_MANAGER = "pr.sistem@example.test"
ASSISTANT = "pr.yardimci@example.test"
MEMBER = "pr.uye@example.test"
OTHER_MEMBER = "pr.uye2@example.test"
DESK_USER = "pr.masa@example.test"
OTHER_ADMIN = "pr.kiraci.yonetici2@example.test"

PEOPLE = (
	(TENANT_ADMIN, [panel_roles.TENANT_ADMIN_ROLE]),
	(OTHER_ADMIN, [panel_roles.TENANT_ADMIN_ROLE]),
	(SYSTEM_MANAGER, ["System Manager"]),
	(ASSISTANT, [ROLE_MEMBER]),
	(MEMBER, [ROLE_MEMBER]),
	(OTHER_MEMBER, [ROLE_MEMBER]),
	(DESK_USER, [ROLE_DESK]),
)


def ensure_role(name: str, desk_access: int) -> None:
	if not frappe.db.exists("Role", name):
		frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": desk_access}).insert()


def reset_user(email: str, roles: list[str]) -> None:
	if frappe.db.exists("User", email):
		doc = frappe.get_doc("User", email)
		doc.set("role_profiles", [])
		doc.set("roles", [{"role": role} for role in roles])
		doc.enabled = 1
		doc.save()
	else:
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Sahte",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert()
	update_password(email, PASSWORD)


class TestTenantAdminAssistant(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_role(ROLE_MEMBER, 0)
		ensure_role(ROLE_DESK, 1)
		if not frappe.db.exists("Role Profile", ADMIN_PROFILE):
			frappe.get_doc(
				{
					"doctype": "Role Profile",
					"role_profile": ADMIN_PROFILE,
					"roles": [{"role": "System Manager"}, {"role": panel_roles.TENANT_ADMIN_ROLE}],
				}
			).insert()
		cls.site = frappe.local.site

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		for email, roles in PEOPLE:
			reset_user(email, roles)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	# --- request helpers ---

	def send(self, client, method: str, path: str, *, body=None, query=None, follow=False):
		headers = {"Accept": "application/json"}
		kwargs = {"path": path, "method": method, "headers": headers, "follow_redirects": follow}
		if body is not None:
			headers["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		if query:
			kwargs["query_string"] = query
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def login(self, user: str):
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": PASSWORD})
		self.assertEqual(response.status_code, 200, response.data[:300])
		return client

	def grant(self, client, user: str):
		return self.send(client, "POST", GRANT, body={"user": user})

	def make_assistant(self):
		response = self.grant(self.login(TENANT_ADMIN), ASSISTANT)
		self.assertEqual(response.status_code, 200, response.data[:300])
		return self.login(ASSISTANT)

	def roles_of(self, user: str) -> set[str]:
		frappe.clear_cache(user=user)
		return set(frappe.get_roles(user)) - {"All", "Guest"}

	def assert_refused(self, response, label: str):
		self.assertIn(response.status_code, (401, 403), f"{label}: {response.status_code}")

	# --- role and profile ---

	def test_role_has_no_desk_access(self):
		self.assertEqual(frappe.db.get_value("Role", panel_roles.ASSISTANT_ROLE, "desk_access"), 0)

	def test_profile_gives_only_the_assistant_role(self):
		profile = frappe.get_doc("Role Profile", panel_roles.ASSISTANT_PROFILE)
		self.assertEqual({row.role for row in profile.roles}, {panel_roles.ASSISTANT_ROLE})

	# --- grant ---

	def test_tenant_admin_gives_the_profile_to_a_member(self):
		response = self.grant(self.login(TENANT_ADMIN), ASSISTANT)
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"]["role_profile"], panel_roles.ASSISTANT_PROFILE)
		doc = frappe.get_doc("User", ASSISTANT)
		self.assertEqual([row.role_profile for row in doc.role_profiles], [panel_roles.ASSISTANT_PROFILE])
		self.assertEqual(doc.user_type, "Website User")
		self.assertEqual(self.roles_of(ASSISTANT), {panel_roles.ASSISTANT_ROLE})

	def test_system_manager_gives_the_profile(self):
		response = self.grant(self.login(SYSTEM_MANAGER), MEMBER)
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(self.roles_of(MEMBER), {panel_roles.ASSISTANT_ROLE})

	def test_holder_has_no_tenant_admin_or_system_manager_role(self):
		self.make_assistant()
		roles = self.roles_of(ASSISTANT)
		self.assertNotIn(panel_roles.TENANT_ADMIN_ROLE, roles)
		self.assertNotIn("System Manager", roles)

	def test_member_without_tenant_admin_cannot_give_the_role(self):
		response = self.grant(self.login(MEMBER), OTHER_MEMBER)
		self.assert_refused(response, "member")
		self.assertEqual(self.roles_of(OTHER_MEMBER), {ROLE_MEMBER})

	def test_grant_cannot_demote_an_admin_or_a_desk_user(self):
		client = self.login(TENANT_ADMIN)
		for target, roles in (
			(SYSTEM_MANAGER, {"System Manager"}),
			(OTHER_ADMIN, {panel_roles.TENANT_ADMIN_ROLE}),
			(DESK_USER, {ROLE_DESK}),
		):
			response = self.grant(client, target)
			self.assertEqual(response.status_code, 417, f"{target}: {response.status_code}")
			self.assertTrue(roles <= self.roles_of(target), target)

	def test_grant_refuses_the_standard_users_and_the_caller(self):
		client = self.login(TENANT_ADMIN)
		for target in ("Administrator", "Guest", TENANT_ADMIN):
			response = self.grant(client, target)
			self.assertEqual(response.status_code, 417, f"{target}: {response.status_code}")
		self.assertIn(panel_roles.TENANT_ADMIN_ROLE, self.roles_of(TENANT_ADMIN))

	def test_grant_refuses_an_unknown_user(self):
		response = self.grant(self.login(TENANT_ADMIN), "pr.yok@example.test")
		self.assertEqual(response.status_code, 404)

	# --- refusals of the role holder ---

	def test_holder_cannot_give_the_role(self):
		response = self.grant(self.make_assistant(), OTHER_MEMBER)
		self.assert_refused(response, "assistant grant")
		self.assertEqual(self.roles_of(OTHER_MEMBER), {ROLE_MEMBER})

	def test_holder_is_refused_on_role_and_permission_endpoints(self):
		"""The G-62 surface: role permission, field level and permission manager endpoints."""
		client = self.make_assistant()
		calls = (
			(
				"POST",
				"platform_core.api.access.set_field_level",
				{"doctype": "ToDo", "fieldname": "description", "permlevel": 1},
			),
			(
				"POST",
				"platform_core.api.access.set_level_access",
				{"doctype": "ToDo", "role": ROLE_MEMBER, "permlevel": 0, "read": 1, "write": 1},
			),
			("GET", "frappe.core.page.permission_manager.permission_manager.get_roles_and_doctypes", None),
			("GET", "frappe.core.page.permission_manager.permission_manager.get_permissions", None),
			(
				"POST",
				"frappe.core.page.permission_manager.permission_manager.add",
				{"parent": "ToDo", "role": panel_roles.ASSISTANT_ROLE, "permlevel": 0},
			),
			(
				"POST",
				"frappe.core.page.permission_manager.permission_manager.update",
				{
					"doctype": "ToDo",
					"role": panel_roles.ASSISTANT_ROLE,
					"permlevel": 0,
					"ptype": "write",
					"value": 1,
				},
			),
			(
				"POST",
				"frappe.core.page.permission_manager.permission_manager.remove",
				{"doctype": "ToDo", "role": "System Manager", "permlevel": 0},
			),
			(
				"GET",
				"frappe.core.page.permission_manager.permission_manager.get_users_with_role",
				{"role": "System Manager"},
			),
		)
		for method, endpoint, body in calls:
			path = f"/api/method/{endpoint}"
			if method == "GET":
				response = self.send(client, "GET", path, query=body)
			else:
				response = self.send(client, "POST", path, body=body)
			self.assert_refused(response, endpoint)

	def test_holder_cannot_write_roles_or_permissions(self):
		client = self.make_assistant()
		writes = (
			("Role", {"role_name": "PR Yeni Rol", "desk_access": 1}),
			("Role Profile", {"role_profile": "PR Yeni Profil", "roles": [{"role": "System Manager"}]}),
			("User Permission", {"user": ASSISTANT, "allow": "User", "for_value": ASSISTANT}),
			("Custom DocPerm", {"parent": "ToDo", "role": panel_roles.ASSISTANT_ROLE, "read": 1, "write": 1}),
			(
				"Has Role",
				{"parent": ASSISTANT, "parenttype": "User", "parentfield": "roles", "role": "System Manager"},
			),
		)
		for doctype, data in writes:
			response = self.send(client, "POST", REST + doctype, body=data)
			self.assert_refused(response, doctype)
		self.assertEqual(self.roles_of(ASSISTANT), {panel_roles.ASSISTANT_ROLE})

	def test_holder_cannot_raise_own_roles(self):
		"""Frappe may accept the save of the own User record. The roles must not change."""
		client = self.make_assistant()
		for body in (
			{"roles": [{"role": "System Manager"}, {"role": panel_roles.TENANT_ADMIN_ROLE}]},
			{"role_profiles": [{"role_profile": ADMIN_PROFILE}]},
			{"role_profile_name": ADMIN_PROFILE},
			{"user_type": "System User"},
		):
			self.send(client, "PUT", f"{REST}User/{ASSISTANT}", body=body)
			self.assertEqual(self.roles_of(ASSISTANT), {panel_roles.ASSISTANT_ROLE}, body)
			self.assertEqual(frappe.db.get_value("User", ASSISTANT, "user_type"), "Website User", body)

	def test_holder_cannot_create_a_user(self):
		client = self.make_assistant()
		response = self.send(
			client, "POST", REST + "User", body={"email": "pr.yeni@example.test", "first_name": "Sahte"}
		)
		self.assert_refused(response, "create user")
		self.assertFalse(frappe.db.exists("User", "pr.yeni@example.test"))

	def test_holder_cannot_delete_a_user(self):
		client = self.make_assistant()
		response = self.send(client, "DELETE", f"{REST}User/{OTHER_MEMBER}")
		self.assert_refused(response, "delete user")
		self.assertTrue(frappe.db.exists("User", OTHER_MEMBER))

	def test_holder_cannot_see_invoices_or_payments(self):
		client = self.make_assistant()
		for doctype in ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Payment Request"):
			if not frappe.db.exists("DocType", doctype):
				continue
			response = self.send(client, "GET", REST + doctype, query={"fields": json.dumps(["name"])})
			self.assert_refused(response, doctype)

	def test_holder_cannot_back_up_or_restore_the_site(self):
		client = self.make_assistant()
		for endpoint, body in (
			("frappe.utils.backups.fetch_latest_backups", None),
			("frappe.utils.backups.get_backup_encryption_key", None),
			("frappe.desk.page.backups.backups.schedule_files_backup", {"user_email": ASSISTANT}),
		):
			response = self.send(client, "POST", f"/api/method/{endpoint}", body=body or {})
			self.assert_refused(response, endpoint)

	def test_holder_cannot_open_desk(self):
		"""G-53: a role without desk access keeps the holder a Website User."""
		client = self.make_assistant()
		for path in ("/desk", "/app"):
			response = self.send(client, "GET", path, follow=True)
			self.assertEqual(response.status_code, 403, f"{path}: {response.status_code}")
