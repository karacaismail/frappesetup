"""Setup step of the HRMS TR Role Profiles (AJA-934, AJA-952).

Written before the code. Frappe 16.56.0 rewrites every file of `fixtures/` on each migrate. A
Role Profile write queues a job that locks the profile. Without a worker the lock stays, and the
next migrate fails with "DocumentLockedError" on "HRT Admin". The profiles are therefore not
fixtures. A setup step opens a profile only when it is missing and leaves an existing one alone.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
FIXTURES = APP_DIR / "fixtures"
PROFILE_FILE = APP_DIR / "role_profile.json"
SETUP_HOOK = "hrms_tr.role_profiles.ensure"
PROFILES = ("HRT Employee", "HRT Manager", "HRT Admin")
# A made-up profile. The test rolls it back.
NEW_PROFILE = "HRT Deneme Profili 952"
NEW_PROFILES = [{"name": NEW_PROFILE, "role_profile": NEW_PROFILE, "roles": [{"role": "HRT Employee"}]}]


def file_profiles():
	return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


class ProfileSourceTest(unittest.TestCase):
	def test_no_fixture_file_holds_a_role_profile(self):
		for path in sorted(FIXTURES.glob("*.json")):
			rows = json.loads(path.read_text(encoding="utf-8"))
			with self.subTest(path=path.name):
				self.assertNotIn("Role Profile", {row.get("doctype") for row in rows})

	def test_profiles_live_in_one_file(self):
		self.assertEqual(tuple(row["name"] for row in file_profiles()), PROFILES)
		for row in file_profiles():
			self.assertEqual(row["role_profile"], row["name"])

	def test_setup_step_runs_after_install_and_after_migrate(self):
		from hrms_tr import hooks

		# Frappe runs `after_install` before it loads the fixtures, so the roles are not there yet.
		# `after_sync` runs after the fixtures of the app (frappe/installer.py, install_app).
		self.assertIn(SETUP_HOOK, hooks.after_sync)
		self.assertIn(SETUP_HOOK, hooks.after_migrate)


try:
	import frappe
	from frappe.tests import IntegrationTestCase
except ImportError:  # pragma: no cover - the integration tests need a Frappe site.
	frappe = None
	IntegrationTestCase = unittest.TestCase


def profile_roles(name):
	return set(
		frappe.get_all("Has Role", filters={"parenttype": "Role Profile", "parent": name}, pluck="role")
	)


@unittest.skipIf(frappe is None, "Frappe is not installed")
class RoleProfileSetupTest(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		from hrms_tr import role_profiles

		self.setup = role_profiles

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def test_every_profile_exists_with_the_roles_of_the_file(self):
		for row in file_profiles():
			with self.subTest(profile=row["name"]):
				self.assertTrue(frappe.db.exists("Role Profile", row["name"]))
				self.assertEqual(profile_roles(row["name"]), {role["role"] for role in row["roles"]})

	def test_missing_profile_is_opened_without_a_lock(self):
		self.assertFalse(frappe.db.exists("Role Profile", NEW_PROFILE))
		with patch.object(self.setup, "load_profiles", return_value=NEW_PROFILES):
			self.setup.ensure()
		self.assertEqual(profile_roles(NEW_PROFILE), {"HRT Employee"})
		# The profile job runs at once and removes its lock. No lock stays for the next migrate.
		self.assertFalse(frappe.get_doc("Role Profile", NEW_PROFILE).is_locked)

	def test_existing_profiles_are_left_alone(self):
		before = {name: frappe.db.get_value("Role Profile", name, "modified") for name in PROFILES}
		with (
			patch.object(frappe.model.document.Document, "save") as save,
			patch.object(frappe.model.document.Document, "insert") as insert,
		):
			self.setup.ensure()
			self.setup.ensure()
		save.assert_not_called()
		insert.assert_not_called()
		for name, modified in before.items():
			self.assertEqual(frappe.db.get_value("Role Profile", name, "modified"), modified, name)
