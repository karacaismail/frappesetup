"""Regression checks for HRMS TR roles and access engine dependencies."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hrms_tr import access, ai_tools, leave, setup

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name):
	return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def raise_with_message(message, *args):
	raise RuntimeError(message)


class RoleFixtureTest(unittest.TestCase):
	def test_roles_do_not_grant_desk_access(self):
		self.assertTrue(all(role["desk_access"] == 0 for role in fixture("01_role.json")))

	def test_manager_and_hr_profiles_keep_employee_role(self):
		for profile in fixture("02_role_profile.json"):
			self.assertIn("HRMS TR Employee", {row["role"] for row in profile["roles"]})

	def test_only_hr_can_cancel_and_amend(self):
		perms = [row for row in fixture("05_custom_docperm.json") if row["permlevel"] == 0]
		self.assertEqual({row["role"] for row in perms if row.get("cancel")}, {"HRMS TR Admin"})
		self.assertEqual({row["role"] for row in perms if row.get("amend")}, {"HRMS TR Admin"})
		rules = fixture("03_access_rule.json")
		self.assertEqual({row["role"] for row in rules if row.get("allow_cancel")}, {"HRMS TR Admin"})


class AccessGateTest(unittest.TestCase):
	def test_active_rule_without_engine_denies_list_and_document(self):
		fake = Mock()
		fake.local = SimpleNamespace()
		fake.get_hooks.return_value = {"*": []}
		fake.db.exists.return_value = True
		with patch.object(access, "frappe", fake):
			self.assertFalse(access.has_permission(None, user="employee@example.test"))
			self.assertIsNotNone(access.query_condition(user="employee@example.test"))

	def test_with_engine_but_no_active_rules_denies_list_and_document(self):
		fake = Mock()
		fake.local = SimpleNamespace()
		fake.get_hooks.side_effect = [
			{"*": ["platform_core.erisim.hooks.query_conditions"]},
			{"*": ["platform_core.erisim.hooks.has_permission"]},
		]
		fake.db.exists.side_effect = [True, False]
		with patch.object(access, "frappe", fake):
			self.assertFalse(access.has_permission(None, user="employee@example.test"))
			self.assertIsNotNone(access.query_condition(user="employee@example.test"))
		self.assertEqual(fake.db.exists.call_count, 2)


class ApprovalReviewTest(unittest.TestCase):
	def test_employee_cannot_change_on_saved_application(self):
		doc = Mock(leave_approver=None, status="Open")
		doc.is_new.return_value = False
		doc.has_value_changed.side_effect = lambda field: field == "employee"
		with patch.object(leave, "frappe") as fake, patch.object(leave, "_", side_effect=lambda text: text):
			fake.throw.side_effect = raise_with_message
			with self.assertRaisesRegex(RuntimeError, "employee cannot change"):
				leave.validate_approval(doc)

	def test_tool_signals_destructive_action_and_describes_name(self):
		(tool,) = ai_tools.declarations()
		self.assertTrue(tool["destructive"])
		self.assertTrue(ai_tools.ApprovalArguments.model_fields["name"].description)


class PortalUserTest(unittest.TestCase):
	def test_native_approver_role_does_not_turn_portal_user_into_system_user(self):
		from hrms_tr import users

		doc = SimpleNamespace(
			name="manager@example.test",
			roles=[SimpleNamespace(role="HRMS TR Manager"), SimpleNamespace(role="Leave Approver")],
			user_type="System User",
			has_desk_access=lambda: False,
		)
		users.keep_portal_user(doc)
		self.assertEqual(doc.user_type, "Website User")
		self.assertEqual([row.role for row in doc.roles], ["HRMS TR Manager"])


class FixtureLifecycleTest(unittest.TestCase):
	def test_migration_rejects_existing_shares(self):
		with (
			patch.object(setup, "frappe") as fake,
			patch.object(setup, "engine_available", return_value=True),
			patch.object(setup, "_", side_effect=lambda text: text),
		):
			fake.db.exists.return_value = True
			fake.throw.side_effect = raise_with_message
			with self.assertRaisesRegex(RuntimeError, "existing Leave Application shares"):
				setup.before_migrate()

	def test_uninstall_dry_run_never_deletes_policy_fixtures(self):
		with patch.object(setup, "frappe") as fake, patch.object(setup, "fixture_rows", return_value=[]):
			fake.local = SimpleNamespace()
			fake.get_installed_apps.return_value = ["hrms_tr"]
			setup.before_uninstall()
			setup.after_uninstall()
			fake.delete_doc.assert_not_called()
			fake.db.commit.assert_not_called()

	def test_uninstalled_policy_cleanup_is_rerunnable(self):
		with patch.object(setup, "frappe") as fake, patch.object(setup, "fixture_rows") as rows:
			fake.get_installed_apps.return_value = []
			fake.db.exists.side_effect = [True, True, True, False]
			rows.side_effect = [[{"doctype": "Access Rule", "name": "HRMS TR Rule"}], [], []] * 2
			setup.remove_policy_fixtures()
			setup.remove_policy_fixtures()
			fake.delete_doc.assert_called_once_with("Access Rule", "HRMS TR Rule", ignore_permissions=True)
			self.assertEqual(fake.db.commit.call_count, 2)

	def test_migration_refreshes_manager_profile_without_waiting_for_a_queue(self):
		user = Mock(
			user_type="Website User",
			roles=[SimpleNamespace(role="HRMS TR Manager")],
			role_profiles=[SimpleNamespace(role_profile="HRMS TR Manager")],
		)
		with patch.object(setup, "frappe") as fake:
			fake.local = SimpleNamespace(hrms_tr_disabled_rules=[])
			fake.get_all.return_value = ["manager@example.test"]
			fake.get_doc.return_value = user
			setup.after_migrate()
		user.save.assert_called_once_with(ignore_permissions=True)
