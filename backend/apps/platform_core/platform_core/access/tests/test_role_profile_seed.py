"""The install step writes only missing panel profiles and leaves no lock (AJA-857).

Written before the code (D-2). Frappe 16.56.0 rewrote every fixture on each migrate. A Role Profile
write queues a job and locks the profile. Without a worker the lock stays and the next migrate
fails with "DocumentLockedError". The install step `ensure_role_profiles` fixes this:

- A profile that exists is not written again.
- A missing profile is inserted. Its job runs at once, so no lock stays and no job is queued.

The tests run with `backend/dev/bin/test platform_core`. That script runs `migrate` once before the
tests, without a worker. Without Frappe the tests are skipped.
"""

import unittest
from unittest import mock

from platform_core.access.tests import panel_roles
from platform_core.access.tests.panel_roles import PANEL_ROLES, PROTECTED_ROLES, IntegrationTestCase, frappe

PROFILE = "Role Profile"


def lock_exists(name: str) -> bool:
	from frappe.utils import file_lock

	return file_lock.lock_exists(frappe.get_doc(PROFILE, name).get_signature())


def profile_roles(name: str) -> list[str]:
	return frappe.get_all("Has Role", filters={"parenttype": PROFILE, "parent": name}, pluck="role")


def seed():
	from platform_core.setup.role_profiles import ensure_role_profiles

	ensure_role_profiles()


@unittest.skipIf(frappe is None, "Frappe is not installed: the tests run with backend/dev/bin/test")
class TestRoleProfileSeed(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		# Outside tests Frappe queues the profile job. Act as a real migrate does.
		self.not_in_test = mock.patch.object(frappe, "in_test", False)
		self.not_in_test.start()
		self.no_install = mock.patch.object(frappe.local.flags, "in_install", None)
		self.no_install.start()

	def tearDown(self):
		self.no_install.stop()
		self.not_in_test.stop()
		frappe.db.rollback()
		super().tearDown()

	def test_migrate_left_the_four_profiles_and_no_lock(self):
		# The test script ran install and one migrate before this test, with no worker.
		for name in PANEL_ROLES:
			self.assertTrue(frappe.db.exists(PROFILE, name), name)
			self.assertEqual(profile_roles(name), [name])
			self.assertFalse(lock_exists(name), f"{name} is locked after migrate")

	def test_existing_profile_is_not_written_again(self):
		before = {name: frappe.db.get_value(PROFILE, name, "modified") for name in PANEL_ROLES}
		with mock.patch("frappe.utils.background_jobs.get_queue") as get_queue:
			for _ in range(3):
				seed()
		get_queue.assert_not_called()
		for name in PANEL_ROLES:
			self.assertEqual(frappe.db.get_value(PROFILE, name, "modified"), before[name], name)
			self.assertFalse(lock_exists(name), name)

	def test_missing_profile_is_inserted_without_a_lock_or_a_queued_job(self):
		name = panel_roles.RESELLER_ASSISTANT
		frappe.delete_doc(PROFILE, name, force=True, ignore_permissions=True)
		self.assertFalse(frappe.db.exists(PROFILE, name))

		with mock.patch("frappe.utils.background_jobs.get_queue") as get_queue:
			seed()
			# A queued job would only be sent on commit.
			frappe.db.commit()  # nosemgrep: frappe-request-commit

		get_queue.assert_not_called()
		self.assertTrue(frappe.db.exists(PROFILE, name))
		self.assertEqual(profile_roles(name), [name])
		self.assertFalse(lock_exists(name), f"{name} is locked after it was inserted")
		# The step restores the install flag it borrowed.
		self.assertIsNone(frappe.local.flags.in_install)

	def test_seeding_three_times_never_raises_a_lock_error(self):
		name = panel_roles.TENANT_ADMIN_ASSISTANT
		frappe.delete_doc(PROFILE, name, force=True, ignore_permissions=True)
		with mock.patch("frappe.utils.background_jobs.get_queue"):
			for _ in range(3):
				seed()
				frappe.db.commit()  # nosemgrep: frappe-request-commit
		for profile in PANEL_ROLES:
			self.assertFalse(lock_exists(profile), profile)

	def test_no_profile_holds_a_protected_role(self):
		for name in PANEL_ROLES:
			self.assertFalse(set(profile_roles(name)) & set(PROTECTED_ROLES), name)
