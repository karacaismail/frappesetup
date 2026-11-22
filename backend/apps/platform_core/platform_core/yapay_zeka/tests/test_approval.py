"""Önizleme ve insan onayı (G-86)."""

from unittest.mock import patch

import frappe
from frappe.core.doctype.user.user import generate_keys
from frappe.utils import add_to_date, now_datetime

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, USER_B, YzTestCase


class TestApproval(YzTestCase):
	def value(self, name: str, fieldname: str = "title"):
		return frappe.db.get_value(DOCTYPE, name, fieldname)

	def test_write_tool_only_opens_a_proposal(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)

		proposal = self.propose_update(client, name, title="Yeni")

		self.assertEqual(proposal["status"], "approval_required")
		self.assertEqual(self.value(name), "Eski")
		change = proposal["preview"]["changes"][0]
		self.assertEqual((change["fieldname"], change["old"], change["new"]), ("title", "Eski", "Yeni"))
		log = self.last_log(tool="update_document", target_name=name)
		self.assertEqual((log.decision, log.stage, log.approval_state), ("allowed", "preview", "pending"))
		self.assertEqual(log.proposal, proposal["proposal_id"])

	def test_approval_executes_once_and_second_use_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)

		first = self.approve(client, proposal_id, digest).json["message"]
		frappe.db.set_value(DOCTYPE, name, "title", "Sonradan")
		second = self.approve(client, proposal_id, digest).json["message"]

		self.assertTrue(first["executed"], first)
		self.assertEqual(first["proposal"]["status"], "consumed")
		self.assertEqual(first["proposal"]["result"], "succeeded")
		self.assertFalse(second["executed"])
		self.assertEqual(second["deny_reason"], "not_pending")
		self.assertEqual(self.value(name), "Sonradan")
		executed = self.last_log(proposal=proposal_id, stage="execute")
		self.assertEqual((executed.decision, executed.result), ("allowed", "succeeded"))
		replay = self.last_log(proposal=proposal_id, stage="approve", decision="denied")
		self.assertEqual(replay.deny_reason, "not_pending")

	def test_execution_links_the_version_record(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)

		# Frappe test kipinde “Version” kaydı yazmaz (`Document._save`). Üretim davranışını
		# görmek için bu tek istekte test kipi kapatılır.
		with patch.object(frappe, "in_test", False):
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertTrue(outcome["executed"], outcome)
		version = self.last_log(proposal=proposal_id, stage="execute").version
		self.assertEqual(frappe.db.get_value("Version", version, ["ref_doctype", "docname"]), (DOCTYPE, name))

	def test_expired_proposal_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		frappe.db.set_value(
			"AI Action Proposal", proposal_id, "expires_at", add_to_date(now_datetime(), seconds=-1)
		)

		outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "expired")
		self.assertEqual(outcome["proposal"]["status"], "expired")
		self.assertEqual(self.value(name), "Eski")

	def test_document_changed_after_preview_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		frappe.set_user(USER_A)
		doc = frappe.get_doc(DOCTYPE, name)
		doc.amount = 99
		doc.save()
		frappe.set_user("Administrator")

		outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "document_changed")
		self.assertEqual(self.value(name), "Eski")

	def test_approval_with_agent_token_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		token = self.issue_token(client)
		proposal = self.call_tool(
			self.anonymous(),
			"update_document",
			{"doctype": DOCTYPE, "name": name, "data": {"title": "Yeni"}},
			token=token,
		)["structuredContent"]
		digest = self.digest_of(client, proposal["proposal_id"])

		response = self.send(
			self.anonymous(),
			"POST",
			"/api/method/platform_core.api.ai.approve_proposal",
			body={"proposal_id": proposal["proposal_id"], "digest": digest},
			headers={"Authorization": f"Bearer {token}"},
		)

		self.assertEqual(response.status_code, 401)
		self.assertEqual(self.value(name), "Eski")
		self.assertEqual(
			frappe.db.get_value("AI Action Proposal", proposal["proposal_id"], "status"), "pending"
		)
		log = self.last_log(deny_reason="token_out_of_scope")
		self.assertEqual((log.user, log.principal, log.decision), (USER_A, "agent_token", "denied"))

	def test_approval_with_api_key_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		keys = generate_keys(USER_A)
		frappe.db.commit()  # nosemgrep

		response = self.send(
			self.anonymous(),
			"POST",
			"/api/method/platform_core.api.ai.approve_proposal",
			body={"proposal_id": proposal_id, "digest": digest},
			headers={"Authorization": f"token {keys['api_key']}:{keys['api_secret']}"},
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.value(name), "Eski")
		log = self.last_log(deny_reason="not_human_session", stage="approve")
		self.assertEqual((log.user, log.principal, log.decision), (USER_A, "other", "denied"))

	def test_another_users_approval_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client_a = self.login(USER_A)
		manager = self.login(MANAGER)
		proposal_id = self.propose_update(client_a, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client_a, proposal_id)

		outcome = self.approve(manager, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "not_owner")
		self.assertEqual(self.value(name), "Eski")

	def test_wrong_digest_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]

		outcome = self.approve(client, proposal_id, "0" * 64).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "digest_mismatch")
		self.assertEqual(self.value(name), "Eski")

	def test_rejected_proposal_cannot_be_approved(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)

		rejected = self.human(client, "POST", "reject_proposal", body={"proposal_id": proposal_id}).json[
			"message"
		]
		outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertEqual(rejected["status"], "rejected")
		self.assertEqual(outcome["deny_reason"], "not_pending")
		self.assertEqual(self.value(name), "Eski")

	def test_permission_lost_after_preview_is_rejected(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		frappe.db.set_value(DOCTYPE, name, "owner", USER_B, update_modified=False)

		outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "permission")
		self.assertEqual(self.value(name), "Eski")

	def test_unknown_result_blocks_new_proposals_until_resolved(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		frappe.db.set_value("AI Action Proposal", proposal_id, {"status": "consumed", "result": "unknown"})

		blocked = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "Baska"}}
		)
		seen = self.call_tool(client, "get_proposal", {"proposal_id": proposal_id})
		resolved = self.human(
			client, "POST", "resolve_proposal", body={"proposal_id": proposal_id, "outcome": "failed"}
		).json["message"]
		again = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "Baska"}}
		)

		self.assert_denied(blocked, "unresolved_unknown")
		self.assertEqual(seen["structuredContent"]["result"], "unknown")
		self.assertEqual(resolved["result"], "failed")
		self.assertFalse(again["isError"], again)

	def test_cancel_of_a_draft_is_rejected_at_preview(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)

		result = self.call_tool(client, "cancel_document", {"doctype": DOCTYPE, "name": name})

		self.assert_denied(result, "invalid_arguments")

	def test_failed_execution_rolls_back_and_is_recorded(self):
		client = self.login(USER_A)
		proposal = self.call_tool(
			client, "create_document", {"doctype": DOCTYPE, "data": {"title": "Hata", "amount": 1}}
		)["structuredContent"]
		# Zorunlu alan kuralı önizlemeden sonra eklenir. Yürütme bu yüzden hata verir.
		frappe.db.set_value("DocField", {"parent": DOCTYPE, "fieldname": "access_token"}, "reqd", 1)
		frappe.clear_cache(doctype=DOCTYPE)
		self.addCleanup(self.clear_reqd)

		outcome = self.approve(client, proposal["proposal_id"]).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "execution_failed")
		self.assertEqual(
			(outcome["proposal"]["status"], outcome["proposal"]["result"]), ("consumed", "failed")
		)
		self.assertEqual(frappe.db.count(DOCTYPE, {"title": "Hata"}), 0)
		log = self.last_log(proposal=proposal["proposal_id"], stage="execute")
		self.assertEqual((log.decision, log.result), ("error", "failed"))

	def clear_reqd(self):
		frappe.db.set_value("DocField", {"parent": DOCTYPE, "fieldname": "access_token"}, "reqd", 0)
		frappe.clear_cache(doctype=DOCTYPE)
		frappe.db.commit()  # nosemgrep

	def test_create_submit_cancel_and_delete_flow(self):
		client = self.login(USER_A)

		created = self.call_tool(
			client, "create_document", {"doctype": DOCTYPE, "data": {"title": "Yeni kayit", "amount": 5}}
		)["structuredContent"]
		self.assertEqual(frappe.db.count(DOCTYPE, {"title": "Yeni kayit"}), 0)
		outcome = self.approve(client, created["proposal_id"]).json["message"]
		name = outcome["proposal"]["result_document"]
		self.addCleanup(self.drop_record, name)
		self.assertEqual(self.value(name, "owner"), USER_A)

		submit = self.call_tool(client, "submit_document", {"doctype": DOCTYPE, "name": name})[
			"structuredContent"
		]
		self.assertEqual(self.value(name, "docstatus"), 0)
		self.assertTrue(self.approve(client, submit["proposal_id"]).json["message"]["executed"])
		self.assertEqual(self.value(name, "docstatus"), 1)

		cancel = self.call_tool(client, "cancel_document", {"doctype": DOCTYPE, "name": name})[
			"structuredContent"
		]
		self.assertTrue(self.approve(client, cancel["proposal_id"]).json["message"]["executed"])
		self.assertEqual(self.value(name, "docstatus"), 2)

		delete = self.call_tool(client, "delete_document", {"doctype": DOCTYPE, "name": name})[
			"structuredContent"
		]
		self.assertTrue(frappe.db.exists(DOCTYPE, name))
		self.assertTrue(self.approve(client, delete["proposal_id"]).json["message"]["executed"])
		self.assertFalse(frappe.db.exists(DOCTYPE, name))

	def test_write_to_another_users_document_is_denied_at_preview(self):
		name = self.make_record(USER_A, title="Eski")
		client_b = self.login(USER_B)

		result = self.call_tool(
			client_b, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "Yeni"}}
		)

		self.assert_denied(result, "permission")
		self.assertEqual(frappe.db.count("AI Action Proposal", {"target_name": name}), 0)

	def test_secret_and_unpermitted_fields_cannot_be_written(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)

		secret = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"vault_code": "x"}}
		)
		permlevel = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"internal_note": "x"}}
		)
		unknown = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"olmayan_alan": "x"}}
		)

		self.assert_denied(secret, "secret_field")
		self.assert_denied(permlevel, "field_not_permitted")
		self.assert_denied(unknown, "invalid_arguments")

	def test_code_and_admin_doctypes_are_closed_to_generic_write_tools(self):
		manager = self.login(MANAGER)

		code = self.call_tool(
			manager,
			"create_document",
			{"doctype": "Server Script", "data": {"name": "yz", "script_type": "API", "script": "pass"}},
		)
		admin = self.call_tool(
			manager, "create_document", {"doctype": "Role", "data": {"role_name": "YZ Yeni"}}
		)
		own = self.call_tool(manager, "delete_document", {"doctype": "AI Action Log", "name": "x"})

		self.assert_denied(code, "blocked_doctype")
		self.assert_denied(admin, "admin_only")
		self.assert_denied(own, "blocked_doctype")

	def test_humans_see_only_their_own_proposals(self):
		name = self.make_record(USER_A)
		client_a = self.login(USER_A)
		client_b = self.login(USER_B)
		proposal_id = self.propose_update(client_a, name, title="Yeni")["proposal_id"]

		listed_a = self.human(client_a, "GET", "list_proposals").json["message"]
		listed_b = self.human(client_b, "GET", "list_proposals").json["message"]
		other = self.human(client_b, "GET", "get_proposal", query={"proposal_id": proposal_id})

		self.assertIn(proposal_id, [row["proposal_id"] for row in listed_a])
		self.assertNotIn(proposal_id, [row["proposal_id"] for row in listed_b])
		self.assertEqual(other.status_code, 403)
