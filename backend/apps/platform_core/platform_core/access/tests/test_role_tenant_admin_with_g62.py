"""The G-62 install step and the panel role fixture make one "Tenant Admin" role (AJA-862).

Two parts make the role. The G-62 step `tenant_admin.ensure_role` inserts the role if it is missing
and adds its permission rows. The fixture `fixtures/role.json` writes the same role on every migrate.
The tests check that both stay in `hooks.py` and that together they make the role once.

The hook tests run without Frappe. The site tests run with `backend/dev/bin/test platform_core`.
"""

import unittest

from platform_core.access.tests.panel_roles import (
	PROFILE_SEED,
	TENANT_ADMIN,
	IntegrationTestCase,
	frappe,
	hook_exports,
	hook_value,
	load_fixture,
)

G62_STEP = "platform_core.access.tenant_admin.ensure_role"


class TestTenantAdminHooks(unittest.TestCase):
	def test_g62_step_and_profile_seed_run_after_install_and_migrate(self):
		for hook in ("after_install", "after_migrate"):
			steps = hook_value(hook)
			self.assertIn(G62_STEP, steps, f"hooks.py {hook} lost the G-62 step")
			self.assertIn(PROFILE_SEED, steps, f"hooks.py {hook} does not seed the profiles")

	def test_fixture_exports_the_same_role(self):
		self.assertTrue(hook_exports("Role", TENANT_ADMIN))
		rows = [row for row in load_fixture("role.json") if row.get("name") == TENANT_ADMIN]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].get("desk_access"), 0)

	def test_setup_wizard_step_stays(self):
		self.assertEqual(hook_value("setup_wizard_complete"), ["platform_core.config.turkey_setup.apply"])


@unittest.skipIf(frappe is None, "Frappe is not installed: the tests run with backend/dev/bin/test")
class TestTenantAdminOnSite(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def role_rows(self) -> int:
		return frappe.db.count("Role", {"role_name": TENANT_ADMIN})

	def permission_rows(self) -> int:
		return frappe.db.count("Custom DocPerm", {"role": TENANT_ADMIN})

	def test_role_exists_once_without_desk_access(self):
		self.assertEqual(self.role_rows(), 1)
		self.assertEqual(frappe.db.get_value("Role", TENANT_ADMIN, "desk_access"), 0)

	def test_both_steps_again_add_no_role_and_no_permission_row(self):
		from frappe.utils.fixtures import sync_fixtures

		from platform_core.access.tenant_admin import ensure_role
		from platform_core.setup.role_profiles import ensure_role_profiles

		rows = self.permission_rows()
		self.assertGreater(rows, 0, "the G-62 step gave the role no permission row")
		for _ in range(2):
			sync_fixtures("platform_core")
			ensure_role_profiles()
			ensure_role()
		self.assertEqual(self.role_rows(), 1)
		self.assertEqual(self.permission_rows(), rows)
		self.assertEqual(frappe.db.count("Role Profile", {"name": TENANT_ADMIN}), 1)
