"""Contract tests for the mobile administration tools."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from pydantic import ValidationError

from platform_core.mobile.store import MobileStore


class MobileAiToolsTest(IntegrationTestCase):
	def setUp(self):
		self.account = self.make_user()
		self.other_account = self.make_user()
		self.installation = self.install(self.account)
		self.other_installation = self.install(self.other_account)

	def make_user(self, account=None):
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": account or f"mobile-ai-{uuid4().hex}@example.test",
					"first_name": "Mobile Test",
					"send_welcome_email": 0,
				}
			)
			.insert()
			.name
		)

	def install(self, account):
		installation = str(uuid4())
		MobileStore().install(
			SimpleNamespace(account=account, scope="mobile", principal="fixture"), installation
		)
		return installation

	def test_hook_declares_approval_required_tools(self):
		from platform_core.mobile.ai_tools import declarations

		self.assertIn("platform_core.mobile.ai_tools.declarations", frappe.get_hooks("ai_tools"))
		tools = {tool["name"]: tool for tool in declarations()}
		self.assertEqual(
			set(tools),
			{
				"list_mobile_installations",
				"revoke_mobile_installation",
				"revoke_all_mobile_installations",
				"preview_mobile_cleanup",
			},
		)
		for name, tool in tools.items():
			model = frappe.get_attr(tool["arguments"])
			self.assertEqual(model.model_config["extra"], "forbid")
			self.assertFalse({"confirm", "approved", "force"} & set(model.model_fields))
			self.assertEqual(tool["roles"], ["System Manager"])
			if name in {"list_mobile_installations", "preview_mobile_cleanup"}:
				self.assertEqual(tool["kind"], "read")
				self.assertFalse(tool.get("destructive", False))
				self.assertNotIn("prepare", tool)
			else:
				self.assertEqual(tool["kind"], "write")
				self.assertIs(tool["destructive"], True)
				self.assertIs(tool["versioned"], True)
				for field in ("handler", "preview", "prepare"):
					self.assertTrue(callable(frappe.get_attr(tool[field])))

	def test_installation_uuid_must_match_the_entire_string(self):
		from platform_core.mobile.ai_tools import InstallationArguments

		for invalid in (f"x{self.installation}", f"{self.installation}x"):
			with self.assertRaises(ValidationError):
				InstallationArguments(installation_id=invalid)

	def test_lists_only_requested_account_without_internal_identity(self):
		from platform_core.mobile.ai_tools import list_installations

		result = list_installations(self.account)
		self.assertEqual(
			result["installations"],
			[{"installation_id": self.installation, "revoked": False, "closure_pending": False}],
		)
		self.assertIsNone(result["next_after"])

	def test_lists_session_closure_states_with_a_bounded_query_count(self):
		from platform_core.mobile.ai_tools import list_installations
		from platform_core.mobile.sessions import _session_key

		pending_sid = str(uuid4())
		closed_sid = str(uuid4())
		expected = {}
		for sid, pending in ((pending_sid, True), (closed_sid, False)):
			frappe.get_doc(
				doctype="PLT Mobile Revoked Session", session_key=_session_key(sid), delivery_pending=int(pending)
			).insert()
			installation = self.install(self.account)
			frappe.db.set_value("PLT Mobile Installation", installation, "session_id", sid)
			expected[installation] = pending

		shared_installation = self.install(self.account)
		frappe.db.set_value("PLT Mobile Installation", shared_installation, "session_id", pending_sid)
		expected[shared_installation] = True
		expected[self.installation] = False

		frappe.get_roles()
		with self.assertQueryCount(2):
			result = list_installations(self.account)
		self.assertEqual(
			{row["installation_id"]: row["closure_pending"] for row in result["installations"]},
			expected,
		)

	def test_single_preview_does_not_mutate_and_execution_sets_cutoff(self):
		from platform_core.mobile import ai_tools

		preview = ai_tools.preview_revoke_installation(installation_id=self.installation)
		self.assertEqual(preview["details"]["installation_ids"], [self.installation])
		self.assertFalse(frappe.db.get_value("PLT Mobile Installation", self.installation, "revoked"))
		plan = ai_tools.prepare_revoke_installation(installation_id=self.installation)
		result = ai_tools.execute_revocation(plan)
		self.assertEqual(result, {"name": preview["target_name"], "revoked": 1})
		self.assertTrue(frappe.db.get_value("PLT Mobile Installation", self.installation, "revoked"))
		self.assertFalse(frappe.db.get_value("PLT Mobile Installation", self.other_installation, "revoked"))
		cutoff = frappe.db.get_value("PLT Mobile Account State", {"account": self.account}, "revoked_through")
		self.assertGreater(int(cutoff), 0)

	def test_all_preview_version_changes_when_target_installations_change(self):
		from platform_core.mobile import ai_tools

		first = ai_tools.preview_revoke_all(account=self.account)
		single = ai_tools.preview_revoke_installation(self.installation)
		for preview in (first, single):
			self.assertEqual(preview["target_doctype"], "PLT Mobile Account State")
			self.assertEqual(preview["target_name"], self.account)
		second = self.install(self.account)
		last = ai_tools.preview_revoke_all(account=self.account)
		self.assertNotEqual(first["target_version"], last["target_version"])
		self.assertCountEqual(last["details"]["installation_ids"], [self.installation, second])
		result = ai_tools.execute_revocation(ai_tools.prepare_revoke_all(account=self.account))
		self.assertEqual(result, {"name": self.account, "revoked": 2})
		self.assertFalse(frappe.db.get_value("PLT Mobile Installation", self.other_installation, "revoked"))

	def test_empty_scope_version_changes_when_same_user_name_is_recreated(self):
		from platform_core.mobile import ai_tools

		account = self.make_user()
		first = ai_tools.preview_revoke_all(account)
		self.assertEqual(first["details"]["installation_ids"], [])
		frappe.delete_doc("User", account)
		self.make_user(account)
		last = ai_tools.preview_revoke_all(account)
		self.assertNotEqual(first["target_version"], last["target_version"])

	def test_revocation_converts_mobile_error_to_validation_error(self):
		from platform_core.mobile import ai_tools
		from platform_core.mobile.protocol import MobileError

		plan = ai_tools.prepare_revoke_installation(self.installation)
		with patch.object(ai_tools.MobileStore, "revoke_targets", side_effect=MobileError("test", 409)):
			with self.assertRaises(frappe.ValidationError):
				ai_tools.execute_revocation(plan)

	def test_cleanup_never_executes_a_delete_or_accepts_write_override(self):
		from platform_core.mobile import ai_tools

		with self.assertRaises(ValidationError):
			ai_tools.CleanupArguments.model_validate({"dry_run": False})
		preview_counts = {"dry_run": True, "removed": 0, "eligible_changes": 1}
		with patch.object(ai_tools, "cleanup", return_value=preview_counts) as cleanup:
			tool = next(tool for tool in ai_tools.declarations() if tool["name"] == "preview_mobile_cleanup")
			result = frappe.get_attr(tool["handler"])(dry_run=True)
		self.assertEqual(result["removed"], 0)
		self.assertTrue(result["dry_run"])
		self.assertTrue(all(call.kwargs == {"dry_run": True} for call in cleanup.call_args_list))

	def test_handlers_and_previews_deny_non_managers(self):
		from platform_core.mobile import ai_tools

		plan = ai_tools.prepare_revoke_installation(self.installation)
		try:
			frappe.set_user(self.other_account)
			for action, arguments in (
				(ai_tools.list_installations, (self.account,)),
				(ai_tools.preview_revoke_installation, (self.installation,)),
				(ai_tools.prepare_revoke_all, (self.account,)),
				(ai_tools.execute_revocation, (plan,)),
				(ai_tools.preview_cleanup, ()),
			):
				with self.subTest(action=action.__name__), self.assertRaises(frappe.PermissionError):
					action(*arguments)
		finally:
			frappe.set_user("Administrator")
