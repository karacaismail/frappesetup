"""Exercise mobile proposals through the shared Frappe HTTP approval layer."""

from datetime import timedelta
from importlib.util import find_spec
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from uuid import uuid4

import frappe
from frappe.utils import now_datetime

from platform_core.mobil.store import MobileStore

AI_LAYER_AVAILABLE = find_spec("platform_core.yapay_zeka.registry") is not None
if AI_LAYER_AVAILABLE:
	from platform_core.yapay_zeka.tests.base import MANAGER, USER_A, YzTestCase
else:
	YzTestCase = TestCase


@skipUnless(AI_LAYER_AVAILABLE, "The shared AI approval layer is not available")
class MobileApprovalTest(YzTestCase):
	def install(self, account):
		name = str(uuid4())
		MobileStore().install(SimpleNamespace(account=account, scope="mobile", principal="fixture"), name)
		return name

	def test_revoke_requires_human_approval_and_keeps_other_installations(self):
		first = self.install(USER_A)
		other = self.install(MANAGER)
		client = self.login(MANAGER)
		token = self.issue_token(client)
		result = self.call_tool(
			self.anonymous(),
			"platform_core_revoke_mobile_installation",
			{"installation_id": first},
			token=token,
		)
		proposal = result["structuredContent"]
		self.assertIn("proposal_id", proposal, result)
		self.assertFalse(frappe.db.get_value("Mobile Installation", first, "revoked"))
		denied = self.send(
			self.anonymous(),
			"POST",
			"/api/method/platform_core.api.ai.approve_proposal",
			body={"proposal_id": proposal["proposal_id"], "digest": "a" * 64},
			headers={"Authorization": f"Bearer {token}"},
		)
		self.assertIn(denied.status_code, (401, 403))
		self.assertFalse(frappe.db.get_value("Mobile Installation", first, "revoked"))
		outcome = self.approve(client, proposal["proposal_id"]).json["message"]
		self.assertTrue(outcome["executed"], outcome)
		self.assertTrue(frappe.db.get_value("Mobile Installation", first, "revoked"))
		self.assertFalse(frappe.db.get_value("Mobile Installation", other, "revoked"))

	def test_mobile_scope_change_rejects_stale_approval(self):
		self.install(USER_A)
		client = self.login(MANAGER)
		result = self.call_tool(client, "platform_core_revoke_all_mobile_installations", {"account": USER_A})
		proposal_id = result["structuredContent"]["proposal_id"]
		new_installation = self.install(USER_A)
		response = self.approve(client, proposal_id)
		outcome = response.json["message"]
		self.assertEqual((outcome["executed"], outcome["deny_reason"]), (False, "document_changed"))
		self.assertFalse(frappe.db.get_value("Mobile Installation", new_installation, "revoked"))

	def test_cleanup_proposal_leaves_expired_rows_untouched_after_approval(self):
		key = uuid4().hex
		MobileStore().remember_operation(key, "a" * 64, {"status": "applied"})
		frappe.db.set_value("Mobile Operation", key, "creation", now_datetime() - timedelta(days=40))
		client = self.login(MANAGER)
		result = self.call_tool(client, "platform_core_preview_mobile_cleanup", {})
		proposal_id = result["structuredContent"]["proposal_id"]
		self.assertTrue(frappe.db.exists("Mobile Operation", key))
		outcome = self.approve(client, proposal_id).json["message"]
		self.assertTrue(outcome["executed"], outcome)
		self.assertTrue(frappe.db.exists("Mobile Operation", key))
