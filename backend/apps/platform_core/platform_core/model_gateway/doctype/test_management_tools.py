"""Exercise gateway registry management through the application tool handlers."""

from decimal import Decimal
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password
from pydantic import ValidationError
from pypika.functions import Cast

from platform_core.model_gateway import management_tools


class TestGatewayManagementTools(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.provider = frappe.get_doc(
			{
				"doctype": "PLT AI Provider",
				"provider_name": f"Fixture {uuid4().hex}",
				"adapter": "openai",
			}
		).insert()
		self.account = frappe.get_doc(
			{
				"doctype": "PLT AI Account",
				"account_name": "Fixture account",
				"provider": self.provider.name,
			}
		).insert()

	def _api(self):
		return frappe.get_doc(
			{
				"doctype": "PLT AI API",
				"account": self.account.name,
				"api_name": "Fixture connection",
				"base_url": "https://old.example.test",
				"auth_type": "api_key",
				"api_key": "fixture-private-credential",
			}
		).insert()

	def test_tools_are_approval_writes_and_updates_are_versioned(self):
		tools = {tool["name"]: tool for tool in management_tools.declare()}
		self.assertEqual(
			set(tools),
			{
				"create_ai_api",
				"update_ai_api",
				"create_ai_account",
				"update_ai_account",
				"reconcile_stale_pending",
			},
		)
		self.assertTrue(all(tool["kind"] == "write" and tool["preview"] for tool in tools.values()))
		self.assertEqual(
			{name for name, tool in tools.items() if tool["versioned"]},
			{"update_ai_api", "update_ai_account", "reconcile_stale_pending"},
		)

	def test_api_tool_rejects_credential_and_disallows_reassignment(self):
		for extra in ({"api_key": "fixture-key"}, {"account": self.account.name}, {"enabled": True}):
			with self.subTest(extra=next(iter(extra))), self.assertRaises(ValidationError):
				management_tools.UpdateApi(name="fixture", **extra)
		for extra in ({"api_key": "fixture-key"}, {"enabled": True}):
			with self.subTest(extra=next(iter(extra))), self.assertRaises(ValidationError):
				management_tools.CreateApi(account=self.account.name, api_name="Fixture", **extra)
		with self.assertRaises(ValidationError):
			management_tools.UpdateAccount(name=self.account.name, provider=self.provider.name)

	def test_api_change_disables_and_clears_credential_only_on_execution(self):
		api = self._api()
		args = {"name": api.name, "base_url": "https://new.example.test"}
		preview = management_tools.preview_update_api(**args)
		self.assertEqual(preview["target_name"], api.name)
		self.assertEqual(preview["target_doctype"], "PLT AI API")
		self.assertTrue(preview["target_version"])
		self.assertTrue(preview["details"]["credential_will_be_cleared"])
		self.assertNotIn("fixture-private-credential", repr(preview))
		self.assertNotIn("api_key", repr(preview))
		self.assertTrue(self._password(api))
		self.assertTrue(frappe.db.get_value("PLT AI API", api.name, "enabled"))

		result = management_tools.update_api(**args)
		self.assertEqual(result, {"name": api.name})
		api.reload()
		self.assertEqual(api.base_url, args["base_url"])
		self.assertFalse(api.enabled)
		self.assertFalse(self._password(api))
		audit = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "PLT AI API", "reference_name": api.name, "comment_type": "Info"},
			pluck="content",
		)
		self.assertIn("Model gateway API credential cleared.", audit)
		with self.assertRaises(ValidationError):
			management_tools.update_api(name=api.name, enabled=True)

	def test_connection_change_and_credential_clear_share_one_transaction(self):
		api = self._api()
		frappe.db.savepoint("gateway_management_update")
		management_tools.update_api(name=api.name, base_url="https://changed.example.test")
		self.assertFalse(self._password(api))
		frappe.db.rollback(save_point="gateway_management_update")
		api.reload()
		self.assertTrue(api.enabled)
		self.assertEqual(api.base_url, "https://old.example.test")
		self.assertTrue(self._password(api))

	def test_harmless_edit_keeps_credential_and_changed_row_has_new_version(self):
		api = self._api()
		args = {"name": api.name, "priority": 8}
		before = management_tools.preview_update_api(**args)
		self.assertFalse(before["details"]["credential_will_be_cleared"])
		management_tools.update_api(**args)
		after = management_tools.preview_update_api(**args)
		self.assertNotEqual(before["target_version"], after["target_version"])
		self.assertTrue(self._password(api))
		self.assertTrue(frappe.db.get_value("PLT AI API", api.name, "enabled"))

	def test_create_api_waits_for_human_to_configure_credential(self):
		args = {"account": self.account.name, "api_name": "New connection", "auth_type": "bearer"}
		preview = management_tools.preview_create_api(**args)
		self.assertEqual(preview["action"], "create")
		self.assertEqual(preview["target_doctype"], "PLT AI API")
		self.assertFalse(frappe.db.exists("PLT AI API", {"api_name": args["api_name"]}))
		result = management_tools.create_api(**args)
		api = frappe.get_doc("PLT AI API", result["name"])
		self.assertFalse(api.enabled)
		self.assertFalse(self._password(api))

	def test_create_and_update_account_use_narrow_fields(self):
		args = {"provider": self.provider.name, "account_name": "New account", "currency": "USD"}
		preview = management_tools.preview_create_account(**args)
		self.assertEqual(preview["target_doctype"], "PLT AI Account")
		self.assertFalse(frappe.db.exists("PLT AI Account", {"account_name": args["account_name"]}))
		result = management_tools.create_account(**args)
		update = {"name": result["name"], "monthly_budget": "120.00", "has_monthly_budget": True}
		self.assertEqual(management_tools.preview_update_account(**update)["target_name"], result["name"])
		self.assertEqual(management_tools.update_account(**update), result)
		self.assertEqual(frappe.db.get_value("PLT AI Account", result["name"], "monthly_budget"), 120)

	def test_account_edit_preserves_exact_existing_budget(self):
		amount = "999999999999.000000001"
		frappe.db.set_value("PLT AI Account", self.account.name, "monthly_budget", Decimal(amount))
		management_tools.update_account(name=self.account.name, account_name="Updated")
		table = frappe.qb.DocType("PLT AI Account")
		result = (
			frappe.qb.from_(table)
			.select(Cast(table.monthly_budget, "CHAR"))
			.where(table.name == self.account.name)
			.run(pluck=True)
		)
		self.assertEqual(result, [amount])

	def test_guest_cannot_preview_or_execute(self):
		user = frappe.session.user
		frappe.set_user("Guest")
		try:
			for action in (
				management_tools.preview_update_account,
				management_tools.update_account,
			):
				with self.assertRaises(frappe.PermissionError):
					action(name=self.account.name, account_name="Denied")
		finally:
			frappe.set_user(user)

	def _password(self, api):
		return get_decrypted_password("PLT AI API", api.name, "api_key", raise_exception=False)
