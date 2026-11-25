"""Setup step of the panel roles and their Role Profiles (G-62, G-168, G-169, G-170, AJA-899).

Written before the code (D-2). The roles and profiles are not fixtures: Frappe would rewrite
them on each migrate, and a Role Profile write leaves a lock (AJA-857). The setup step opens a
record only when it is missing and leaves an existing record alone.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

ROLES = (
	"Tenant Admin",
	"Tenant Admin Assistant",
	"Reseller Admin",
	"Reseller Assistant",
	"Platform Operator",
)
PROFILES = ("Tenant Admin", "Tenant Admin Assistant", "Reseller Admin", "Reseller Assistant")
PROTECTED_ROLES = ("System Manager", "Administrator")
# A made-up role and profile. The test rolls them back.
NEW_ROLE = "PLT Deneme Paneli 899"
NEW_ROLES = [{"name": NEW_ROLE, "role_name": NEW_ROLE, "desk_access": 0}]
NEW_PROFILES = [{"name": NEW_ROLE, "role_profile": NEW_ROLE, "roles": [{"role": NEW_ROLE}]}]


def profile_roles(name: str) -> list[str]:
	return frappe.get_all("Has Role", filters={"parenttype": "Role Profile", "parent": name}, pluck="role")


class TestPanelRoleSetup(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		from platform_core.setup import panel_roles

		self.setup = panel_roles

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def test_every_role_and_profile_exists_after_install(self):
		for role in ROLES:
			self.assertTrue(frappe.db.exists("Role", role), role)
		self.assertEqual(frappe.db.get_value("Role", "Platform Operator", "desk_access"), 1)
		for profile in PROFILES:
			self.assertTrue(frappe.db.exists("Role Profile", profile), profile)
			self.assertEqual(profile_roles(profile), [profile])
			self.assertEqual(frappe.db.get_value("Role", profile, "desk_access"), 0)

	def test_no_role_and_no_profile_holds_system_manager(self):
		self.assertFalse(set(ROLES) & set(PROTECTED_ROLES))
		for profile in PROFILES:
			self.assertFalse(set(profile_roles(profile)) & set(PROTECTED_ROLES), profile)

	def test_missing_role_and_profile_are_opened(self):
		self.assertFalse(frappe.db.exists("Role", NEW_ROLE))
		with (
			patch.object(self.setup, "load_roles", return_value=NEW_ROLES),
			patch.object(self.setup, "load_profiles", return_value=NEW_PROFILES),
		):
			self.setup.ensure()

		self.assertEqual(frappe.db.get_value("Role", NEW_ROLE, "desk_access"), 0)
		self.assertEqual(profile_roles(NEW_ROLE), [NEW_ROLE])
		# The profile job runs at once and removes its lock. No lock stays for the next migrate.
		self.assertFalse(frappe.get_doc("Role Profile", NEW_ROLE).is_locked)

	def test_existing_records_are_left_alone(self):
		before = {
			(doctype, name): frappe.db.get_value(doctype, name, "modified")
			for doctype, names in (("Role", ROLES), ("Role Profile", PROFILES))
			for name in names
		}
		with (
			patch.object(frappe.model.document.Document, "save") as save,
			patch.object(frappe.model.document.Document, "insert") as insert,
		):
			self.setup.ensure()
			self.setup.ensure()
		save.assert_not_called()
		insert.assert_not_called()
		for (doctype, name), modified in before.items():
			self.assertEqual(frappe.db.get_value(doctype, name, "modified"), modified, name)
		for profile in PROFILES:
			self.assertFalse(frappe.get_doc("Role Profile", profile).is_locked, profile)

	def test_existing_role_keeps_its_own_settings(self):
		# A System Manager may have changed the role on the site. The setup step does not undo it.
		frappe.db.set_value("Role", "Reseller Assistant", "two_factor_auth", 1)
		self.setup.ensure()
		self.assertEqual(frappe.db.get_value("Role", "Reseller Assistant", "two_factor_auth"), 1)
