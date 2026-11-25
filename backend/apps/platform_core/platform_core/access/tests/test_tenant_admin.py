"""G-62: the “Tenant Admin” role manages roles and permissions of its own site (AJA-802).

The holder is a Website User, as the panel's users are. The holder manages roles, role profiles,
permission rows, user permissions and access rules. The holder can neither give nor change the
“System Manager” and “Administrator” roles.

A tenant is its own Frappe site. A session and the role live on one site only, so the holder
works only in its own tenant.
"""

import inspect
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password

from platform_core.access import tenant_admin
from platform_core.access.tests.base import PASSWORD

API = "/api/method/platform_core.api.access."
HOLDER = "ta.yonetici@example.test"
PLAIN = "ta.uye@example.test"
SYSTEM_MANAGER_USER = "ta.sistem@example.test"
CUSTOM_ROLE = "TA Deneme Rol"
OTHER_ROLE = "TA Ikinci Rol"
PROFILE = "TA Deneme Profil"
# A business type without stored permission rows of its own, so the copy of the standard rows can be seen.
PERMISSION_TYPE = "Sales Partner Type"
DESK_ROLE = "TA Masa Rol"
CUSTOM_TYPE = "TA Ozel Tur"
RULE_TYPE = "ToDo"
PROTECTED = ("System Manager", "Administrator")


def _user(email: str, roles: list[str]) -> None:
	if frappe.db.exists("User", email):
		doc = frappe.get_doc("User", email)
		doc.set("roles", [{"role": role} for role in roles])
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			doctype="User",
			email=email,
			first_name=email.split("@")[0],
			send_welcome_email=0,
			roles=[{"role": role} for role in roles],
		).insert(ignore_permissions=True)
	update_password(email, PASSWORD)


class TestTenantAdmin(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site = frappe.local.site
		frappe.set_user("Administrator")
		# An interrupted run can leave a profile link behind. The users are saved below.
		cls.clean()
		tenant_admin.ensure_permissions()
		for role in (CUSTOM_ROLE, OTHER_ROLE):
			if not frappe.db.exists("Role", role):
				frappe.get_doc(doctype="Role", role_name=role, desk_access=0).insert()
		if not frappe.db.exists("Role", DESK_ROLE):
			frappe.get_doc(doctype="Role", role_name=DESK_ROLE, desk_access=1).insert()
		if not frappe.db.exists("DocType", CUSTOM_TYPE):
			# A type a System Manager makes on the site. Such types are business types.
			frappe.get_doc(
				doctype="DocType",
				name=CUSTOM_TYPE,
				module="Custom",
				custom=1,
				fields=[{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
				permissions=[{"role": "System Manager", "read": 1, "write": 1, "create": 1}],
			).insert()
		_user(HOLDER, [tenant_admin.ROLE])
		_user(PLAIN, [CUSTOM_ROLE])
		_user(SYSTEM_MANAGER_USER, ["System Manager"])
		frappe.db.commit()  # nosemgrep: frappe-test-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.clean()
		frappe.db.commit()  # nosemgrep: frappe-test-commit
		super().tearDownClass()

	@staticmethod
	def clean():
		frappe.db.delete("PLT Access Rule", {"role": ("in", [CUSTOM_ROLE, OTHER_ROLE, *PROTECTED])})
		frappe.db.delete("PLT Access Rule", {"title": ("like", "TA %")})
		frappe.db.delete("User Permission", {"user": ("in", [PLAIN, SYSTEM_MANAGER_USER])})
		frappe.db.delete("User Role Profile", {"role_profile": PROFILE})
		frappe.db.set_value("User", {"role_profile_name": PROFILE}, "role_profile_name", None)
		if frappe.db.exists("Role Profile", PROFILE):
			frappe.delete_doc("Role Profile", PROFILE, ignore_permissions=True, force=True)
		frappe.db.delete("Custom DocPerm", {"parent": ("in", [PERMISSION_TYPE, CUSTOM_TYPE])})
		frappe.db.delete("Custom DocPerm", {"role": ("in", [CUSTOM_ROLE, OTHER_ROLE])})
		frappe.db.delete("Role", {"name": "TA Yeni Rol"})
		frappe.clear_cache()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.clean()
		frappe.db.commit()  # nosemgrep: frappe-test-commit

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self.clean()
		# A test can change the roles of these two users. The next test starts from the same roles.
		_user(PLAIN, [CUSTOM_ROLE])
		_user(SYSTEM_MANAGER_USER, ["System Manager"])
		frappe.db.commit()  # nosemgrep: frappe-test-commit
		super().tearDown()

	# --- request helpers ---

	def send(self, client, method: str, path: str, *, body=None, query=None):
		headers = {"Accept": "application/json"}
		kwargs = {"path": path, "method": method, "headers": headers}
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

	def login(self, user: str = HOLDER):
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": PASSWORD})
		self.assertEqual(response.status_code, 200)
		return client

	def resource(self, client, method: str, doctype: str, name: str | None = None, body=None, query=None):
		path = "/api/resource/" + quote(doctype)
		if name is not None:
			path += "/" + quote(name)
		return self.send(client, method, path, body=body, query=query)

	def custom_row(self, role: str, parent: str = PERMISSION_TYPE) -> str | None:
		return frappe.db.get_value("Custom DocPerm", {"parent": parent, "role": role, "permlevel": 0})

	# --- installation ---

	def test_role_is_set_up_on_install_and_migrate(self):
		# AJA-899: the setup step opens the role when it is missing. The permission rows follow.
		setup = "platform_core.setup.panel_roles.ensure"
		hook = "platform_core.access.tenant_admin.ensure_permissions"
		for name in ("after_install", "after_migrate"):
			hooks = frappe.get_hooks(name)
			self.assertIn(setup, hooks, name)
			self.assertIn(hook, hooks, name)
			self.assertLess(hooks.index(setup), hooks.index(hook), name)
		self.assertTrue(frappe.db.exists("Role", tenant_admin.ROLE))
		# The panel's users stay Website Users. A desk role would make them System Users.
		self.assertEqual(frappe.db.get_value("Role", tenant_admin.ROLE, "desk_access"), 0)

	def test_role_is_defined_only_in_the_setup_step(self):
		# One definition: `setup/role.json`. Neither a fixture nor this module opens the role.
		self.assertFalse(hasattr(tenant_admin, "ensure_role"))
		self.assertNotIn('doctype="Role"', inspect.getsource(tenant_admin))
		fixture = Path(frappe.get_app_path("platform_core", "fixtures", "role.json"))
		fixture_rows = json.loads(fixture.read_text()) if fixture.exists() else []
		self.assertNotIn(tenant_admin.ROLE, {row["name"] for row in fixture_rows})
		setup = Path(frappe.get_app_path("platform_core", "setup", "role.json"))
		rows = [row for row in json.loads(setup.read_text()) if row["name"] == tenant_admin.ROLE]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["desk_access"], 0)

	def test_permission_rows_wait_for_the_role(self):
		# Without the role the function writes nothing.
		exists = frappe.db.exists

		def no_role(doctype, *args, **kwargs):
			if doctype == "Role":
				return None
			return exists(doctype, *args, **kwargs)

		with (
			patch.object(frappe.db, "exists", side_effect=no_role),
			patch.object(tenant_admin, "add_permission") as add,
			patch.object(tenant_admin, "setup_custom_perms") as copy,
		):
			tenant_admin.ensure_permissions()
		add.assert_not_called()
		copy.assert_not_called()

	def test_role_gets_its_permission_rows_once(self):
		tenant_admin.ensure_permissions()
		tenant_admin.ensure_permissions()
		for doctype, ptypes in tenant_admin.GRANTS.items():
			rows = frappe.get_all(
				"Custom DocPerm",
				filters={"parent": doctype, "role": tenant_admin.ROLE, "permlevel": 0, "if_owner": 0},
				fields=["name", *ptypes],
			)
			self.assertEqual(len(rows), 1, doctype)
			for ptype in ptypes:
				self.assertEqual(rows[0][ptype], 1, (doctype, ptype))
			# The standard rows of the type were copied, so the other roles keep their permission.
			self.assertTrue(
				frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "System Manager"}), doctype
			)
		for (doctype, level), ptypes in tenant_admin.LEVEL_GRANTS.items():
			row = {"parent": doctype, "role": tenant_admin.ROLE, "permlevel": level, "if_owner": 0}
			for ptype in ptypes:
				self.assertEqual(
					frappe.db.get_value("Custom DocPerm", row, ptype), 1, (doctype, level, ptype)
				)
		self.assertEqual(frappe.db.get_value("User", HOLDER, "user_type"), "Website User")

	# --- read endpoints ---

	def test_holder_reads_role_and_permission_endpoints(self):
		client = self.login()
		for doctype in ("Role", "Role Profile", "User Permission", "PLT Access Rule"):
			response = self.resource(client, "GET", doctype, query={"limit_page_length": 5})
			self.assertEqual(response.status_code, 200, (doctype, response.data[:300]))
		roles = self.resource(client, "GET", "Role", query={"limit_page_length": 0})
		self.assertIn("System Manager", {row["name"] for row in roles.json["data"]})

	def test_plain_website_user_cannot_read_role_endpoints(self):
		client = self.login(PLAIN)
		for doctype in ("Role", "Role Profile", "User Permission", "PLT Access Rule"):
			response = self.resource(client, "GET", doctype)
			self.assertEqual(response.status_code, 403, doctype)

	# --- Role ---

	def test_holder_creates_and_changes_an_ordinary_role(self):
		client = self.login()
		created = self.resource(client, "POST", "Role", body={"role_name": "TA Yeni Rol", "desk_access": 0})
		changed = self.resource(client, "PUT", "Role", "TA Yeni Rol", body={"two_factor_auth": 1})

		self.assertEqual(created.status_code, 200, created.data[:300])
		self.assertEqual(changed.status_code, 200, changed.data[:300])

	def test_holder_cannot_change_or_delete_a_protected_role(self):
		client = self.login()
		for role in PROTECTED:
			changed = self.resource(client, "PUT", "Role", role, body={"two_factor_auth": 1})
			deleted = self.resource(client, "DELETE", "Role", role)
			self.assertEqual(changed.status_code, 403, role)
			self.assertEqual(deleted.status_code, 403, role)
			self.assertTrue(frappe.db.exists("Role", role))
		self.assertEqual(frappe.db.get_value("Role", "System Manager", "two_factor_auth"), 0)

	def test_holder_cannot_give_a_role_desk_access(self):
		"""Desk access would make the role's users System Users and lift the panel's method list."""
		response = self.resource(self.login(), "PUT", "Role", CUSTOM_ROLE, body={"desk_access": 1})

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.db.get_value("Role", CUSTOM_ROLE, "desk_access"), 0)

	# --- Role Profile ---

	def test_holder_manages_a_role_profile_of_ordinary_roles(self):
		client = self.login()
		body = {"role_profile": PROFILE, "roles": [{"role": CUSTOM_ROLE}]}
		created = self.resource(client, "POST", "Role Profile", body=body)
		changed = self.resource(
			client,
			"PUT",
			"Role Profile",
			PROFILE,
			body={"roles": [{"role": CUSTOM_ROLE}, {"role": OTHER_ROLE}]},
		)

		self.assertEqual(created.status_code, 200, created.data[:300])
		self.assertEqual(changed.status_code, 200, changed.data[:300])
		stored = frappe.get_all(
			"Has Role", filters={"parent": PROFILE, "parenttype": "Role Profile"}, pluck="role"
		)
		self.assertEqual(set(stored), {CUSTOM_ROLE, OTHER_ROLE})

	def test_holder_cannot_put_a_protected_role_in_a_role_profile(self):
		client = self.login()
		for role in PROTECTED:
			body = {"role_profile": PROFILE, "roles": [{"role": role}]}
			response = self.resource(client, "POST", "Role Profile", body=body)
			self.assertEqual(response.status_code, 403, (role, response.data[:400]))
			self.assertFalse(frappe.db.exists("Role Profile", PROFILE))

	def test_holder_cannot_change_a_role_profile_that_holds_a_protected_role(self):
		frappe.get_doc(
			doctype="Role Profile", role_profile=PROFILE, roles=[{"role": "System Manager"}]
		).insert(ignore_permissions=True)
		client = self.login()

		changed = self.resource(
			client, "PUT", "Role Profile", PROFILE, body={"roles": [{"role": CUSTOM_ROLE}]}
		)
		deleted = self.resource(client, "DELETE", "Role Profile", PROFILE)

		self.assertEqual(changed.status_code, 403)
		self.assertEqual(deleted.status_code, 403)
		self.assertEqual(
			frappe.get_all(
				"Has Role", filters={"parent": PROFILE, "parenttype": "Role Profile"}, pluck="role"
			),
			["System Manager"],
		)

	# --- role permission rows (Frappe keeps them in “Custom DocPerm”) ---

	def rows(self, client, doctype: str = PERMISSION_TYPE):
		return self.send(client, "GET", API + "list_role_permissions", query={"doctype": doctype})

	def set_row(self, client, role: str, permissions: dict, doctype: str = PERMISSION_TYPE, **key):
		body = {"doctype": doctype, "role": role, "permissions": permissions, **key}
		return self.send(client, "POST", API + "set_role_permission", body=body)

	def remove_row(self, client, role: str, doctype: str = PERMISSION_TYPE, **key):
		body = {"doctype": doctype, "role": role, **key}
		return self.send(client, "POST", API + "remove_role_permission", body=body)

	def test_holder_reads_the_permission_rows_of_a_type(self):
		response = self.rows(self.login())

		self.assertEqual(response.status_code, 200, response.data[:300])
		message = response.json["message"]
		self.assertFalse(message["stored"])
		standard = set(frappe.get_all("DocPerm", filters={"parent": PERMISSION_TYPE}, pluck="role"))
		self.assertEqual({row["role"] for row in message["rows"]}, standard)

	def test_plain_website_user_cannot_read_or_change_permission_rows(self):
		client = self.login(PLAIN)

		self.assertEqual(self.rows(client).status_code, 403)
		self.assertEqual(self.set_row(client, CUSTOM_ROLE, {"read": 1}).status_code, 403)
		self.assertEqual(self.remove_row(client, CUSTOM_ROLE).status_code, 403)
		self.assertIsNone(self.custom_row(CUSTOM_ROLE))

	def test_holder_adds_a_permission_row_and_the_standard_rows_are_kept(self):
		standard = set(frappe.get_all("DocPerm", filters={"parent": PERMISSION_TYPE}, pluck="role"))

		response = self.set_row(self.login(), CUSTOM_ROLE, {"read": 1})

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"]["role"], CUSTOM_ROLE)
		self.assertEqual(response.json["message"]["read"], 1)
		stored = set(frappe.get_all("Custom DocPerm", filters={"parent": PERMISSION_TYPE}, pluck="role"))
		self.assertEqual(stored, standard | {CUSTOM_ROLE})

	def test_holder_changes_and_removes_a_permission_row_of_an_ordinary_role(self):
		client = self.login()
		self.set_row(client, CUSTOM_ROLE, {"read": 1})

		changed = self.set_row(client, CUSTOM_ROLE, {"write": 1})
		self.assertEqual(changed.status_code, 200, changed.data[:300])
		self.assertEqual(frappe.db.get_value("Custom DocPerm", self.custom_row(CUSTOM_ROLE), "write"), 1)

		removed = self.remove_row(client, CUSTOM_ROLE)
		self.assertEqual(removed.status_code, 200, removed.data[:300])
		self.assertIsNone(self.custom_row(CUSTOM_ROLE))

	def test_holder_cannot_give_a_protected_role_a_permission_row(self):
		client = self.login()
		for role in PROTECTED:
			response = self.set_row(client, role, {"read": 1}, permlevel=1)
			self.assertEqual(response.status_code, 403, role)
			self.assertFalse(
				frappe.db.exists("Custom DocPerm", {"parent": PERMISSION_TYPE, "role": role, "permlevel": 1})
			)

	def test_holder_cannot_change_or_remove_a_permission_row_of_a_protected_role(self):
		frappe.permissions.setup_custom_perms(PERMISSION_TYPE)
		name = self.custom_row("System Manager")
		self.assertTrue(name)
		client = self.login()

		changed = self.set_row(client, "System Manager", {"read": 0})
		removed = self.remove_row(client, "System Manager")

		self.assertEqual(changed.status_code, 403)
		self.assertEqual(removed.status_code, 403)
		self.assertEqual(frappe.db.get_value("Custom DocPerm", name, ["role", "read"]), ("System Manager", 1))

	def test_guard_holds_when_a_row_is_saved_without_the_endpoints(self):
		"""Another path that saves the row as the holder meets the same guard."""
		frappe.permissions.setup_custom_perms(PERMISSION_TYPE)
		name = self.custom_row("System Manager")
		frappe.set_user(HOLDER)
		doc = frappe.get_doc("Custom DocPerm", name)
		doc.role = CUSTOM_ROLE
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		ordinary = frappe.new_doc("Custom DocPerm")
		ordinary.update({"parent": PERMISSION_TYPE, "role": CUSTOM_ROLE, "permlevel": 0, "read": 1})
		ordinary.insert(ignore_permissions=True)
		ordinary.role = "Administrator"
		with self.assertRaises(frappe.PermissionError):
			ordinary.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
		frappe.set_user("Administrator")

	def test_holder_cannot_widen_the_permission_management_types(self):
		"""Rows of the role and permission types would let the holder widen its own power."""
		client = self.login()
		for parent in ("Role", "Role Profile", "User Permission", "PLT Access Rule", "User", "DocType"):
			response = self.set_row(client, CUSTOM_ROLE, {"read": 1, "write": 1}, doctype=parent)
			self.assertEqual(response.status_code, 403, parent)
			self.assertIsNone(self.custom_row(CUSTOM_ROLE, parent), parent)

	def test_permission_rows_reject_unknown_rights_and_levels(self):
		client = self.login()

		self.assertEqual(self.set_row(client, CUSTOM_ROLE, {"rule_all": 1}).status_code, 417)
		self.assertEqual(self.set_row(client, CUSTOM_ROLE, {"read": 1}, permlevel=10).status_code, 417)
		self.assertEqual(self.set_row(client, "TA Olmayan Rol", {"read": 1}).status_code, 404)
		self.assertEqual(self.rows(client, "TA Olmayan Tur").status_code, 404)
		self.assertIsNone(self.custom_row(CUSTOM_ROLE))

	# --- User Permission ---

	def test_holder_manages_a_user_permission_of_an_ordinary_user(self):
		client = self.login()
		body = {"user": PLAIN, "allow": "Role", "for_value": CUSTOM_ROLE}

		created = self.resource(client, "POST", "User Permission", body=body)
		name = frappe.db.get_value("User Permission", {"user": PLAIN})
		deleted = self.resource(client, "DELETE", "User Permission", name)

		self.assertEqual(created.status_code, 200, created.data[:300])
		self.assertIn(deleted.status_code, (200, 202))

	def test_holder_cannot_narrow_a_system_manager(self):
		body = {"user": SYSTEM_MANAGER_USER, "allow": "Role", "for_value": CUSTOM_ROLE}

		response = self.resource(self.login(), "POST", "User Permission", body=body)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(frappe.db.exists("User Permission", {"user": SYSTEM_MANAGER_USER}))

	# --- Access Rule ---

	def rule(self, role: str) -> dict:
		return {
			"title": f"TA {role}",
			"is_active": 0,
			"document_type": RULE_TYPE,
			"role": role,
			"scope": "all",
			"allow_read": 1,
		}

	def test_holder_manages_an_access_rule_of_an_ordinary_role(self):
		client = self.login()
		created = self.resource(client, "POST", "PLT Access Rule", body=self.rule(CUSTOM_ROLE))
		name = frappe.db.get_value("PLT Access Rule", {"role": CUSTOM_ROLE})
		changed = self.resource(client, "PUT", "PLT Access Rule", name, body={"allow_write": 1})

		self.assertEqual(created.status_code, 200, created.data[:300])
		self.assertEqual(changed.status_code, 200, changed.data[:300])

	def test_holder_cannot_write_an_access_rule_for_a_protected_role(self):
		client = self.login()
		for role in PROTECTED:
			response = self.resource(client, "POST", "PLT Access Rule", body=self.rule(role))
			self.assertEqual(response.status_code, 403, role)
			self.assertFalse(frappe.db.exists("PLT Access Rule", {"role": role}))

	def test_holder_cannot_change_an_access_rule_of_a_protected_role(self):
		doc = frappe.get_doc(doctype="PLT Access Rule", **self.rule("System Manager")).insert()
		client = self.login()

		changed = self.resource(client, "PUT", "PLT Access Rule", doc.name, body={"role": CUSTOM_ROLE})
		deleted = self.resource(client, "DELETE", "PLT Access Rule", doc.name)

		self.assertEqual(changed.status_code, 403)
		self.assertEqual(deleted.status_code, 403)
		self.assertEqual(frappe.db.get_value("PLT Access Rule", doc.name, "role"), "System Manager")

	# --- giving a role to a user ---

	def test_holder_cannot_give_a_protected_role_to_a_user(self):
		"""The holder has no write permission on users. The guard holds on every other path too."""
		response = self.resource(
			self.login(), "PUT", "User", PLAIN, body={"roles": [{"role": "System Manager"}]}
		)
		self.assertEqual(response.status_code, 403)

		frappe.set_user(HOLDER)
		for role in PROTECTED:
			doc = frappe.get_doc("User", PLAIN)
			doc.append("roles", {"role": role})
			with self.assertRaises(frappe.PermissionError):
				doc.save(ignore_permissions=True)
		doc = frappe.get_doc("User", SYSTEM_MANAGER_USER)
		doc.set("roles", [{"role": CUSTOM_ROLE}])
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		frappe.set_user("Administrator")
		self.assertNotIn("System Manager", frappe.get_roles(PLAIN))

	def test_system_manager_still_gives_a_protected_role(self):
		frappe.set_user(SYSTEM_MANAGER_USER)
		doc = frappe.get_doc("User", PLAIN)
		doc.append("roles", {"role": "System Manager"})
		doc.save(ignore_permissions=True)

		self.assertIn("System Manager", frappe.get_roles(PLAIN))

	# --- explain_permission ---

	def test_holder_gets_the_explanation(self):
		response = self.send(
			self.login(),
			"GET",
			"/api/method/platform_core.api.access.explain_permission",
			query={"doctype": "User", "name": HOLDER, "ptype": "read"},
		)

		self.assertEqual(response.status_code, 200, response.data[:300])
		message = response.json["message"]
		self.assertEqual(message["user"], HOLDER)
		self.assertTrue(message["allowed"])

	def test_plain_website_user_does_not_get_the_explanation(self):
		response = self.send(
			self.login(PLAIN),
			"GET",
			"/api/method/platform_core.api.access.explain_permission",
			query={"doctype": "User", "name": PLAIN, "ptype": "read"},
		)

		self.assertEqual(response.status_code, 403)

	def test_holder_does_not_explain_another_users_permission(self):
		response = self.send(
			self.login(),
			"GET",
			"/api/method/platform_core.api.access.explain_permission",
			query={"doctype": "User", "name": PLAIN, "user": SYSTEM_MANAGER_USER},
		)

		self.assertEqual(response.status_code, 403)

	# --- second review (AJA-802): indirect ways to System Manager power ---

	def test_holder_cannot_open_framework_or_platform_types(self):
		"""Script, sign-in, token and settings types would carry the holder to System Manager power."""
		client = self.login()
		for parent in (
			"Client Script",
			"Website Script",
			"Custom HTML Block",
			"OAuth Bearer Token",
			"OAuth Client",
			"Social Login Key",
			"System Settings",
			"Note",
			"PLT Identity Link",
			"PLT AI API",
		):
			if not frappe.db.exists("DocType", parent):
				continue
			response = self.set_row(client, CUSTOM_ROLE, {"read": 1, "create": 1, "write": 1}, doctype=parent)
			self.assertEqual(response.status_code, 403, parent)
			self.assertIsNone(self.custom_row(CUSTOM_ROLE, parent), parent)
		frappe.set_user(HOLDER)
		row = frappe.new_doc("Custom DocPerm")
		row.update({"parent": "Client Script", "role": CUSTOM_ROLE, "permlevel": 0, "read": 1, "write": 1})
		with self.assertRaises(frappe.PermissionError):
			row.insert(ignore_permissions=True)
		frappe.set_user("Administrator")

	def test_holder_cannot_give_the_standard_roles_a_permission_row(self):
		client = self.login()
		for role in ("Guest", "All", "Script Manager"):
			response = self.set_row(client, role, {"read": 1})
			self.assertEqual(response.status_code, 403, role)
			self.assertIsNone(self.custom_row(role), role)

	def test_holder_cannot_put_a_power_role_in_a_role_profile(self):
		"""A desk role or “Script Manager” in a profile would make its users System Users."""
		client = self.login()
		for role in ("Script Manager", DESK_ROLE, "Guest", "All"):
			body = {"role_profile": PROFILE, "roles": [{"role": role}]}
			response = self.resource(client, "POST", "Role Profile", body=body)
			self.assertEqual(response.status_code, 403, role)
			self.assertFalse(frappe.db.exists("Role Profile", PROFILE))

	def test_holder_cannot_give_a_power_role_to_a_user_on_another_path(self):
		frappe.set_user(HOLDER)
		for role in ("Script Manager", DESK_ROLE):
			doc = frappe.get_doc("User", PLAIN)
			doc.append("roles", {"role": role})
			with self.assertRaises(frappe.PermissionError):
				doc.save(ignore_permissions=True)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.get_roles(PLAIN).count(DESK_ROLE), 0)

	def test_holder_cannot_change_or_delete_its_own_role(self):
		client = self.login()
		changed = self.resource(client, "PUT", "Role", tenant_admin.ROLE, body={"disabled": 1})
		deleted = self.resource(client, "DELETE", "Role", tenant_admin.ROLE)

		self.assertEqual(changed.status_code, 403)
		self.assertEqual(deleted.status_code, 403)
		self.assertEqual(frappe.db.get_value("Role", tenant_admin.ROLE, "disabled"), 0)
		self.assertIn(tenant_admin.ROLE, frappe.get_roles(HOLDER))

	def test_profile_change_reaches_its_users_and_skips_a_system_manager(self):
		frappe.get_doc(doctype="Role Profile", role_profile=PROFILE, roles=[{"role": CUSTOM_ROLE}]).insert()
		for email in (PLAIN, SYSTEM_MANAGER_USER):
			doc = frappe.get_doc("User", email)
			doc.append("role_profiles", {"role_profile": PROFILE})
			doc.flags.ignore_permissions = True
			# The profile sync of a System Manager save keeps the direct role of this test user.
			doc.save()
		frappe.db.set_value(
			"Has Role", {"parent": SYSTEM_MANAGER_USER, "role": CUSTOM_ROLE}, "role", "System Manager"
		)
		frappe.clear_cache()
		self.assertIn("System Manager", frappe.get_roles(SYSTEM_MANAGER_USER))

		response = self.resource(
			self.login(),
			"PUT",
			"Role Profile",
			PROFILE,
			body={"roles": [{"role": CUSTOM_ROLE}, {"role": OTHER_ROLE}]},
		)

		self.assertEqual(response.status_code, 200, response.data[:300])
		frappe.clear_cache()
		self.assertEqual(set(frappe.get_roles(PLAIN)) & {CUSTOM_ROLE, OTHER_ROLE}, {CUSTOM_ROLE, OTHER_ROLE})
		self.assertIn("System Manager", frappe.get_roles(SYSTEM_MANAGER_USER))
		self.assertNotIn(OTHER_ROLE, frappe.get_roles(SYSTEM_MANAGER_USER))

	def test_a_text_zero_does_not_turn_a_right_on(self):
		response = self.set_row(self.login(), CUSTOM_ROLE, {"read": 1, "write": "0"})

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(frappe.db.get_value("Custom DocPerm", self.custom_row(CUSTOM_ROLE), "write"), 0)

	# --- third review (AJA-802) ---

	def test_holder_gives_a_permission_row_on_a_custom_type_of_the_site(self):
		response = self.set_row(self.login(), CUSTOM_ROLE, {"read": 1}, doctype=CUSTOM_TYPE)

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertTrue(self.custom_row(CUSTOM_ROLE, CUSTOM_TYPE))

	def test_holder_cannot_change_a_role_that_is_not_plain(self):
		"""Turning off desk access, 2FA or the role itself would hit the role's users."""
		client = self.login()
		for body in ({"desk_access": 0}, {"two_factor_auth": 1}, {"disabled": 1}):
			response = self.resource(client, "PUT", "Role", DESK_ROLE, body=body)
			self.assertEqual(response.status_code, 403, body)
		deleted = self.resource(client, "DELETE", "Role", DESK_ROLE)

		self.assertEqual(deleted.status_code, 403)
		self.assertEqual(frappe.db.get_value("Role", DESK_ROLE, ["desk_access", "disabled"]), (1, 0))

	def test_holder_does_not_list_the_rows_of_a_closed_type(self):
		response = self.rows(self.login(), "Client Script")

		self.assertEqual(response.status_code, 403)

	def test_holder_cannot_take_a_role_that_is_not_plain_from_a_user(self):
		user = frappe.get_doc("User", PLAIN)
		user.append("roles", {"role": "Script Manager"})
		user.save()
		frappe.set_user(HOLDER)
		doc = frappe.get_doc("User", PLAIN)
		doc.set("roles", [row for row in doc.roles if row.role != "Script Manager"])

		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		frappe.set_user("Administrator")
