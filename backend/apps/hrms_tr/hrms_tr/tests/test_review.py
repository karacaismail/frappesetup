"""Regression checks for HRMS TR roles and access engine dependencies."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from hrms_tr import access, ai_tools, leave, setup

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name):
	return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def profiles():
	# The Role Profiles are not fixtures (AJA-934). `hrms_tr.role_profiles` opens them from this file.
	return json.loads((FIXTURES.parent / "role_profile.json").read_text(encoding="utf-8"))


def raise_with_message(message, *args):
	raise RuntimeError(message)


class RoleFixtureTest(unittest.TestCase):
	def test_roles_do_not_grant_desk_access(self):
		self.assertTrue(all(role["desk_access"] == 0 for role in fixture("01_role.json")))

	def test_manager_and_hr_profiles_keep_employee_role(self):
		for profile in profiles():
			self.assertIn("HRT Employee", {row["role"] for row in profile["roles"]})

	def test_employee_permissions_only_grant_read(self):
		# HRMS asks for Employee read before a leave is opened. The two panel roles open leaves (AJA-947).
		permissions = [
			row
			for row in fixture("05_custom_docperm.json")
			if row["parent"] == "Employee" and row["permlevel"] == 0
		]
		self.assertEqual(
			{row["role"] for row in permissions}, {"HRT Admin", "Tenant Admin", "Tenant Admin Assistant"}
		)
		for permission in permissions:
			with self.subTest(role=permission["role"]):
				self.assertEqual({key for key, value in permission.items() if value == 1}, {"read"})

	def test_personal_employee_fields_are_on_their_own_level(self):
		# The two panel roles read level 0 of an employee. The personal fields are above it (AJA-1024).
		setters = {
			(row["doc_type"], row["field_name"], row["property"]): row["value"]
			for row in fixture("04_property_setter.json")
		}
		self.assertTrue(setup.EMPLOYEE_PERSONAL_FIELDS)
		for field in setup.EMPLOYEE_PERSONAL_FIELDS:
			with self.subTest(field=field):
				self.assertEqual(
					setters.get(("Employee", field, "permlevel")), str(setup.EMPLOYEE_PERSONAL_LEVEL)
				)
		# The preferred address can be a copy of the personal address.
		self.assertIn("prefered_email", setup.EMPLOYEE_PERSONAL_FIELDS)
		for child, fields in setup.EMPLOYEE_PERSONAL_CHILD_FIELDS.items():
			for field in fields:
				with self.subTest(child=child, field=field):
					self.assertEqual(
						setters.get((child, field, "permlevel")), str(setup.EMPLOYEE_PERSONAL_LEVEL)
					)
		# Names stay on level 0: the leave list shows who asked for the leave.
		for field in ("first_name", "employee_name", "company", "department"):
			self.assertNotIn(("Employee", field, "permlevel"), setters)

	def test_only_the_hr_roles_read_the_personal_employee_fields(self):
		# Every role that read the whole employee record before keeps the personal fields.
		expected = {
			"Employee": {"read"},
			"Employee Self Service": {"read", "write"},
			"HR Manager": {"read", "write"},
			"HR User": {"read", "write"},
			"HRT Admin": {"read"},
		}
		rows = [
			row
			for row in fixture("05_custom_docperm.json")
			if row["parent"] == "Employee" and row["permlevel"] == setup.EMPLOYEE_PERSONAL_LEVEL
		]
		granted = {row["role"]: {k for k, v in row.items() if v == 1 and k != "permlevel"} for row in rows}
		self.assertEqual(granted, expected)
		self.assertEqual(len(rows), len(expected))

	def test_only_authorized_roles_can_cancel_and_amend(self):
		perms = [row for row in fixture("05_custom_docperm.json") if row["permlevel"] == 0]
		self.assertEqual(
			{row["role"] for row in perms if row.get("cancel")},
			{"HRT Admin", "System Manager", "HR Manager"},
		)
		self.assertEqual({row["role"] for row in perms if row.get("amend")}, {"HRT Admin"})
		rules = fixture("03_access_rule.json")
		self.assertEqual(
			{row["role"] for row in rules if row.get("allow_cancel")},
			{"HRT Admin", "System Manager", "HR Manager"},
		)


class LinkSearchPermissionTest(unittest.TestCase):
	"""A role that fills in a leave application can search its "Leave Type" link field."""

	ROLES = frozenset(
		{
			"HRT Employee",
			"HRT Manager",
			"HRT Admin",
			"System Manager",
			"Tenant Admin",
			"Tenant Admin Assistant",
		}
	)

	def test_every_leave_role_can_select_leave_types_only(self):
		rows = [row for row in fixture("05_custom_docperm.json") if row["parent"] == "Leave Type"]
		self.assertEqual({row["role"] for row in rows}, self.ROLES)
		for row in rows:
			with self.subTest(role=row["role"]):
				self.assertEqual(row["permlevel"], 0)
				# "select" lists names in a link search. It does not open the record.
				self.assertEqual({key for key, value in row.items() if value == 1}, {"select"})

	def test_install_and_migrate_keep_standard_leave_type_permissions(self):
		# Frappe ignores the standard rows once a custom row exists, so the copy must come first.
		for step in (setup.check_install, setup.before_migrate):
			with (
				self.subTest(step=step.__name__),
				patch.object(setup, "frappe") as fake,
				patch.object(setup, "setup_custom_perms") as copy,
			):
				fake.db.exists.return_value = False
				fake.get_all.return_value = []
				with (
					patch.object(setup, "require_access_engine"),
					patch.object(setup, "require_unshared_applications"),
					patch.object(setup, "fixture_rows", return_value=[]),
				):
					step()
				fake.throw.assert_not_called()
				copied = [call.args[0] for call in copy.call_args_list]
				self.assertIn("Leave Type", copied)
				self.assertIn("Employee", copied)


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
			{"*": ["platform_core.access.hooks.query_conditions"]},
			{"*": ["platform_core.access.hooks.has_permission"]},
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
		with (
			patch.object(leave, "frappe") as fake,
			patch.object(leave, "_", side_effect=lambda text, context=None: text),
		):
			fake.throw.side_effect = raise_with_message
			with self.assertRaisesRegex(RuntimeError, "employee cannot change"):
				leave.validate_approval(doc)

	def test_tool_signals_destructive_action_and_describes_name(self):
		(tool,) = ai_tools.declarations()
		self.assertTrue(tool["destructive"])
		self.assertTrue(ai_tools.ApprovalArguments.model_fields["name"].description)


class PortalUserTest(unittest.TestCase):
	def test_leave_names_only_change_for_new_portal_requests(self):
		for user, role, name, uses_uuid in (
			("employee@example.test", "HRT Employee", None, True),
			("employee@example.test", "HRT Employee", "HR-LAP-EXISTING", False),
			("Administrator", "HRT Employee", None, False),
			("operations@example.test", "HR Manager", None, False),
		):
			with self.subTest(user=user, name=name), patch.object(leave, "frappe") as framework:
				framework.session.user = user
				framework.get_roles.return_value = [role]
				doc = SimpleNamespace(name=name)
				leave.name_portal_leave(doc)
				if uses_uuid:
					self.assertEqual(UUID(doc.name).version, 7)
				else:
					self.assertEqual(doc.name, name)

	def test_native_approver_role_does_not_turn_portal_user_into_system_user(self):
		from hrms_tr import users

		doc = SimpleNamespace(
			name="manager@example.test",
			roles=[SimpleNamespace(role="HRT Manager"), SimpleNamespace(role="Leave Approver")],
			user_type="System User",
			has_desk_access=lambda: False,
		)
		users.keep_portal_user(doc)
		self.assertEqual(doc.user_type, "Website User")
		self.assertEqual([row.role for row in doc.roles], ["HRT Manager"])


class FixtureLifecycleTest(unittest.TestCase):
	def test_migration_rejects_existing_shares(self):
		with (
			patch.object(setup, "frappe") as fake,
			patch.object(setup, "engine_available", return_value=True),
			patch.object(setup, "_", side_effect=lambda text, context=None: text),
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
			rows.side_effect = [[{"doctype": "PLT Access Rule", "name": "HRMS TR Rule"}], [], []] * 2
			setup.remove_policy_fixtures()
			setup.remove_policy_fixtures()
			fake.delete_doc.assert_called_once_with("PLT Access Rule", "HRMS TR Rule")
			self.assertEqual(fake.db.commit.call_count, 2)

	def test_migration_refreshes_manager_profile_without_waiting_for_a_queue(self):
		user = Mock()
		name = "manager@example.test"
		with patch.object(setup, "frappe") as fake:
			fake.local = SimpleNamespace(hrms_tr_disabled_rules=[])
			fake.get_all.side_effect = [
				[name],
				[SimpleNamespace(name=name, user_type="Website User")],
				[],
				[name],
				[],
			]
			fake.get_doc.return_value = user
			setup.after_migrate()
		user.save.assert_called_once_with()


class OperationsRoleTest(unittest.TestCase):
	def test_operations_roles_have_native_permissions_and_matching_access_rules(self):
		permissions = fixture("05_custom_docperm.json")
		rules = fixture("03_access_rule.json")
		for role in ("System Manager", "HR Manager"):
			with self.subTest(role=role):
				native = {
					row["permlevel"]: row
					for row in permissions
					if row["role"] == role and row["parent"] == "Leave Application"
				}
				self.assertEqual(set(native), {0, 1})
				for operation in ("read", "write", "submit", "cancel"):
					self.assertEqual(native[0][operation], 1)
				self.assertEqual(native[1]["read"], 1)
				self.assertEqual(native[1]["write"], 1)
				rule = next(row for row in rules if row["role"] == role)
				self.assertEqual(rule["scope"], "all")
				self.assertTrue(all(rule[f"allow_{name}"] for name in ("read", "write", "submit", "cancel")))
		# Native HRMS roles get no leave rows. Their Employee rows only keep the personal fields (AJA-1024).
		leave_roles = {row["role"] for row in permissions if row["parent"] == "Leave Application"}
		self.assertFalse({"Employee", "Leave Approver", "HR User"} & leave_roles)

	def test_operations_roles_can_cancel_natively(self):
		with patch.object(leave, "frappe") as fake:
			fake.session.user = "operations@example.test"
			for role in ("System Manager", "HR Manager"):
				fake.get_roles.return_value = [role]
				leave.validate_cancellation(None)
			fake.throw.assert_not_called()


class LeaveReportTest(unittest.TestCase):
	def test_unsafe_reports_are_denied_before_the_native_role_check(self):
		from hrms_tr.hrms_endpoints import ReportAccess

		class NativeReport:
			def is_permitted(self):
				return True

		class Report(ReportAccess, NativeReport):
			pass

		report = Report()
		for name in ("Employee Leave Balance Summary", "Employee Leave Balance", "Leave Ledger"):
			report.name = name
			self.assertFalse(report.is_permitted())
		report.name = "Unrelated Report"
		self.assertTrue(report.is_permitted())

	def test_saved_prepared_report_cannot_return_blocked_report_content(self):
		from hrms_tr import hrms_endpoints

		class NativePreparedReport:
			def get_prepared_data(self, with_file_name=False):
				return "stored result"

		class PreparedReport(hrms_endpoints.PreparedReportAccess, NativePreparedReport):
			report_name = "Leave Ledger"

		with patch.object(hrms_endpoints, "deny_legacy_leave_query", side_effect=PermissionError):
			with self.assertRaises(PermissionError):
				PreparedReport().get_prepared_data(with_file_name=True)

	def test_old_private_report_attachments_cannot_use_the_file_download_path(self):
		from hrms_tr import hrms_endpoints

		class NativeFile:
			def is_downloadable(self):
				return True

		class File(hrms_endpoints.PreparedReportFileAccess, NativeFile):
			attached_to_doctype = "Prepared Report"
			attached_to_name = "PREPARED-TEST"

		with patch.object(hrms_endpoints, "frappe") as fake:
			fake.db.get_value.return_value = "Leave Ledger"
			self.assertFalse(File().is_downloadable())


class PortalRoutingTest(unittest.TestCase):
	def test_website_user_is_denied_native_hrms_portals(self):
		from hrms_tr import users

		with (
			patch.object(users, "frappe") as fake,
			patch.object(users, "_", side_effect=lambda text, context=None: text),
		):
			fake.session.user = "employee@example.test"
			fake.get_cached_value.return_value = "Website User"
			fake.throw.side_effect = raise_with_message
			for path in ("/hrms", "/hrms/leaves", "/hr/team", "/roster"):
				with self.subTest(path=path):
					fake.request.path = path
					with self.assertRaisesRegex(RuntimeError, "tenant portal"):
						users.require_tenant_portal()

	def test_panel_and_system_operations_are_unaffected(self):
		from hrms_tr import users

		with patch.object(users, "frappe") as fake:
			fake.session.user = "manager@example.test"
			fake.request.path = "/panel"
			users.require_tenant_portal()
			fake.get_cached_value.assert_not_called()
			fake.get_cached_value.return_value = "System User"
			fake.request.path = "/hrms"
			users.require_tenant_portal()
			fake.throw.assert_not_called()

	def test_options_request_does_not_require_a_session(self):
		from hrms_tr import users

		with patch.object(users, "frappe") as fake:
			fake.request.path = "/hrms"
			fake.request.method = "OPTIONS"
			fake.session = None
			users.require_tenant_portal()
			fake.get_cached_value.assert_not_called()


class PortalMigrationBatchTest(unittest.TestCase):
	def test_batches_users_and_loads_only_accounts_requiring_a_save(self):
		manager = Mock()
		with patch.object(setup, "frappe") as fake:
			fake.local = SimpleNamespace(hrms_tr_disabled_rules=[])
			fake.get_all.side_effect = [
				["employee@example.test", "manager@example.test"],
				[
					SimpleNamespace(name="employee@example.test", user_type="Website User"),
					SimpleNamespace(name="manager@example.test", user_type="Website User"),
				],
				[SimpleNamespace(parent="employee@example.test", role="HRT Employee")],
				["manager@example.test"],
				[],
			]
			fake.get_doc.return_value = manager
			setup.after_migrate()
		page, *_batch, last = fake.get_all.call_args_list
		self.assertEqual(page.kwargs["limit_page_length"], 100)
		self.assertEqual(page.kwargs["order_by"], "parent asc")
		self.assertIn(["parent", ">", "manager@example.test"], last.kwargs["filters"])
		fake.get_doc.assert_called_once_with("User", "manager@example.test")
		manager.save.assert_called_once_with()
