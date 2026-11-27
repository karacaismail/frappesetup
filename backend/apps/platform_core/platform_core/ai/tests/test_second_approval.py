"""R3 proposals need a second person's approval (AJA-1003).

The owner gives the first approval. Nothing runs then. A second person with write permission on
the target gives the second approval. Then the server checks the record and the preview again
and runs the action. The owner's second approval counts as one approval.
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from platform_core.ai.tests.base import DOCTYPE, MANAGER, SECOND_MANAGER, USER_A, USER_B, AiTestCase
from platform_core.ai.tests.test_risk_level import with_risk_tools

AWAITING = "awaiting_second_approval"
PROPOSAL = "PLT AI Action Proposal"
# The value of a permlevel 1 field. Only System Managers may read it (AJA-1077).
HIDDEN_OLD = "Gizli-eski-not-4821"
HIDDEN_NEW = "Gizli-yeni-not-9364"


class TestSecondApproval(AiTestCase):
	def setUp(self):
		super().setUp()
		patcher = with_risk_tools()
		patcher.start()
		self.addCleanup(patcher.stop)

	def r3_proposal(self, client, name: str, title: str = "Yeni") -> str:
		result = self.call_tool(client, "plt_high_declared_note", {"name": name, "title": title})
		self.assertFalse(result["isError"], result)
		self.assertEqual(result["structuredContent"]["risk_level"], "R3")
		return result["structuredContent"]["proposal_id"]

	def stored(self, proposal_id: str) -> dict:
		return frappe.db.get_value(
			PROPOSAL,
			proposal_id,
			["status", "result", "first_approved_at", "second_approver", "second_approved_at"],
			as_dict=True,
		)

	def title(self, name: str) -> str:
		return frappe.db.get_value(DOCTYPE, name, "title")

	def first_approved(self) -> tuple[str, str, object]:
		"""A record of user A, its R3 proposal and the owner's first approval."""
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.r3_proposal(owner, name)
		response = self.approve(owner, proposal_id)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return name, proposal_id, owner

	def waiting_for(self, client) -> list[dict]:
		response = self.human(client, "GET", "list_second_approvals")
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["message"]["proposals"]

	def second_digest(self, client, proposal_id: str) -> str:
		row = next(row for row in self.waiting_for(client) if row["proposal_id"] == proposal_id)
		return row["digest"]

	# --- first approval ---

	def test_owner_first_approval_does_not_run_an_r3_proposal(self):
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.r3_proposal(owner, name)

		response = self.approve(owner, proposal_id)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		outcome = response.json["message"]
		self.assertFalse(outcome["executed"], outcome)
		self.assertIsNone(outcome["deny_reason"])
		self.assertEqual(outcome["proposal"]["status"], AWAITING)
		self.assertTrue(outcome["proposal"]["first_approved_at"])
		self.assertIsNone(outcome["proposal"]["second_approver"])
		self.assertEqual(self.title(name), "Eski")
		stored = self.stored(proposal_id)
		self.assertEqual((stored.status, stored.result or ""), (AWAITING, ""))
		self.assertTrue(stored.first_approved_at)
		log = self.last_log(stage="approve", proposal=proposal_id, decision="allowed")
		self.assertIsNotNone(log)
		self.assertEqual(log.approval_state, AWAITING)
		self.assertEqual(log.user, USER_A)

	def test_owner_approving_twice_does_not_run_an_r3_proposal(self):
		name, proposal_id, owner = self.first_approved()

		response = self.approve(owner, proposal_id)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		outcome = response.json["message"]
		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(outcome["deny_reason"], "second_approver_required")
		self.assertEqual(self.title(name), "Eski")
		self.assertEqual(self.stored(proposal_id).status, AWAITING)
		self.assertIsNone(self.stored(proposal_id).second_approver)
		self.assertIsNotNone(
			self.last_log(stage="approve", proposal=proposal_id, deny_reason="second_approver_required")
		)

	def test_another_person_cannot_give_the_first_approval(self):
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.r3_proposal(owner, name)
		digest = self.digest_of(owner, proposal_id)

		response = self.approve(self.login(MANAGER), proposal_id, digest)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(digest, response.get_data(as_text=True))
		self.assertEqual(self.stored(proposal_id).status, "pending")
		self.assertEqual(self.title(name), "Eski")

	# --- second approval ---

	def test_second_person_runs_the_proposal_and_is_recorded(self):
		name, proposal_id, _owner = self.first_approved()
		second = self.login(MANAGER)

		response = self.approve(second, proposal_id, self.second_digest(second, proposal_id))

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		outcome = response.json["message"]
		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual(outcome["proposal"]["second_approver"], MANAGER)
		self.assertTrue(outcome["proposal"]["second_approved_at"])
		self.assertEqual(self.title(name), "Yeni")
		stored = self.stored(proposal_id)
		self.assertEqual((stored.status, stored.result), ("consumed", "succeeded"))
		self.assertEqual(stored.second_approver, MANAGER)
		self.assertTrue(stored.second_approved_at)
		approve_log = self.last_log(stage="approve", proposal=proposal_id, user=MANAGER, decision="allowed")
		execute_log = self.last_log(stage="execute", proposal=proposal_id, user=MANAGER, decision="allowed")
		self.assertIsNotNone(approve_log)
		self.assertIsNotNone(execute_log)

	def test_person_without_write_permission_cannot_give_the_second_approval(self):
		name, proposal_id, owner = self.first_approved()
		digest = self.digest_of(owner, proposal_id)

		response = self.approve(self.login(USER_B), proposal_id, digest)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(digest, response.get_data(as_text=True))
		self.assertEqual(self.title(name), "Eski")
		stored = self.stored(proposal_id)
		self.assertEqual(stored.status, AWAITING)
		self.assertIsNone(stored.second_approver)
		log = self.last_log(stage="approve", proposal=proposal_id, deny_reason="not_second_approver")
		self.assertIsNotNone(log)
		self.assertEqual(log.user, USER_B)

	def test_second_person_refused_by_the_preview_does_not_end_the_proposal(self):
		from unittest.mock import patch

		from platform_core.ai.tests import sample_tools

		name, proposal_id, _owner = self.first_approved()
		second = self.login(MANAGER)
		digest = self.second_digest(second, proposal_id)

		def refuse(*_args, **_kwargs):
			raise frappe.PermissionError("No permission for this action.")

		with patch.object(sample_tools, "preview_title", refuse):
			response = self.approve(second, proposal_id, digest)

		# The second person may not do the action. That person cannot end the owner's proposal.
		self.assertEqual(response.status_code, 403)
		self.assertNotIn(digest, response.get_data(as_text=True))
		stored = self.stored(proposal_id)
		self.assertEqual(stored.status, AWAITING)
		self.assertIsNone(stored.second_approver)
		self.assertEqual(self.title(name), "Eski")
		self.assertIsNotNone(
			self.last_log(
				stage="approve", proposal=proposal_id, user=MANAGER, deny_reason="not_second_approver"
			)
		)

	def test_second_person_needs_the_permission_of_the_action(self):
		from unittest.mock import patch

		from platform_core.ai import proposals

		asked = []

		def has_permission(doctype, ptype="read", doc=None, user=None, **_kwargs):
			asked.append(ptype)
			return True

		frappe.set_user(MANAGER)
		# This direct call shares frappe.local with earlier tests, unlike an HTTP request.
		# Load this test's declared tools and restore the earlier request cache afterwards.
		with (
			patch.object(frappe.local, "yz_tools", None, create=True),
			patch.object(frappe, "has_permission", has_permission),
		):
			for action, ptype in (
				("create", "create"),
				("update", "write"),
				("submit", "submit"),
				("cancel", "cancel"),
				("delete", "delete"),
				("app_tool", "write"),
			):
				row = frappe._dict(
					user=USER_A,
					tool="plt_high_declared_note",
					target_doctype=DOCTYPE,
					target_name=None,
					preview_json=f'{{"action": "{action}", "summary": "x"}}',
				)
				self.assertIsNone(proposals.second_approver_problem(row), action)
				self.assertEqual(asked[-1], ptype, action)

	def test_approval_fields_cannot_be_written_outside_their_step(self):
		name = self.make_record(USER_A, title="Eski")
		proposal_id = self.r3_proposal(self.login(USER_A), name)
		doc = frappe.get_doc(PROPOSAL, proposal_id)

		# A pending proposal has no second approver. The owner is never the second approver.
		doc.second_approver = MANAGER
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		frappe.db.rollback()
		doc = frappe.get_doc(PROPOSAL, proposal_id)
		doc.first_approved_at = now_datetime()
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		frappe.db.rollback()
		doc = frappe.get_doc(PROPOSAL, proposal_id)
		doc.status, doc.first_approved_at = AWAITING, now_datetime()
		doc.save(ignore_permissions=True)
		doc.second_approver = USER_A
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		frappe.db.rollback()

	def test_second_approval_checks_the_record_again(self):
		name, proposal_id, _owner = self.first_approved()
		frappe.db.set_value(DOCTYPE, name, "title", "Baska")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		second = self.login(MANAGER)

		response = self.approve(second, proposal_id, self.second_digest(second, proposal_id))

		outcome = response.json["message"]
		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(outcome["deny_reason"], "document_changed")
		self.assertEqual(self.title(name), "Baska")
		self.assertEqual(self.stored(proposal_id).status, "rejected")

	def test_second_approval_needs_the_digest(self):
		name, proposal_id, _owner = self.first_approved()

		response = self.approve(self.login(MANAGER), proposal_id, "0" * 64)

		outcome = response.json["message"]
		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(outcome["deny_reason"], "digest_mismatch")
		self.assertEqual(self.title(name), "Eski")

	def test_second_approval_after_expiry_does_not_run(self):
		name, proposal_id, _owner = self.first_approved()
		second = self.login(MANAGER)
		digest = self.second_digest(second, proposal_id)
		frappe.db.set_value(PROPOSAL, proposal_id, "expires_at", add_to_date(now_datetime(), seconds=-5))
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		response = self.approve(second, proposal_id, digest)

		outcome = response.json["message"]
		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(outcome["deny_reason"], "expired")
		self.assertEqual(self.title(name), "Eski")

	def test_owner_can_reject_while_the_second_approval_waits(self):
		name, proposal_id, owner = self.first_approved()

		response = self.human(owner, "POST", "reject_proposal", body={"proposal_id": proposal_id})

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(self.stored(proposal_id).status, "rejected")
		self.assertEqual(self.title(name), "Eski")

	def test_second_approver_fields_do_not_change_after_they_are_set(self):
		_name, proposal_id, _owner = self.first_approved()
		second = self.login(MANAGER)
		self.approve(second, proposal_id, self.second_digest(second, proposal_id))

		doc = frappe.get_doc(PROPOSAL, proposal_id)
		doc.second_approver = USER_B

		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		frappe.db.rollback()
		self.assertEqual(self.stored(proposal_id).second_approver, MANAGER)

	# --- the waiting list ---

	def test_waiting_list_shows_r3_proposals_to_a_permitted_second_person(self):
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.r3_proposal(owner, name)
		manager = self.login(MANAGER)

		self.assertNotIn(proposal_id, [row["proposal_id"] for row in self.waiting_for(manager)])
		self.approve(owner, proposal_id)

		row = next(row for row in self.waiting_for(manager) if row["proposal_id"] == proposal_id)
		self.assertEqual(row["status"], AWAITING)
		self.assertEqual(row["risk_level"], "R3")
		self.assertEqual(row["digest"], self.digest_of(owner, proposal_id))
		self.assertNotIn(proposal_id, [row["proposal_id"] for row in self.waiting_for(owner)])
		self.assertNotIn(proposal_id, [row["proposal_id"] for row in self.waiting_for(self.login(USER_B))])

	def test_own_list_filters_proposals_that_wait_for_a_second_approval(self):
		_name, proposal_id, owner = self.first_approved()

		listed = self.human(owner, "GET", "list_proposals", query={"status": AWAITING})

		self.assertEqual(listed.status_code, 200, listed.get_data(as_text=True))
		self.assertIn(proposal_id, [row["proposal_id"] for row in listed.json["message"]["proposals"]])

	# --- fields the second person may not read (AJA-1077) ---

	def hidden_field_proposal(self) -> tuple[str, str, str]:
		"""A record of user A with a permlevel 1 value and a manager's first-approved R3 proposal.

		User A may write the record as its owner. User A may not read the permlevel 1 field.
		"""
		name = self.make_record(USER_A, title="Eski")
		frappe.db.set_value(DOCTYPE, name, "internal_note", HIDDEN_OLD)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		owner = self.login(MANAGER)
		result = self.call_tool(owner, "plt_high_internal_note", {"name": name, "internal_note": HIDDEN_NEW})
		self.assertFalse(result["isError"], result)
		proposal_id = result["structuredContent"]["proposal_id"]
		digest = self.digest_of(owner, proposal_id)
		response = self.approve(owner, proposal_id, digest)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(self.stored(proposal_id).status, AWAITING)
		return name, proposal_id, digest

	def assert_hidden(self, text: str) -> None:
		self.assertNotIn(HIDDEN_OLD, text)
		self.assertNotIn(HIDDEN_NEW, text)

	def test_waiting_list_hides_a_proposal_with_a_field_the_reader_may_not_read(self):
		_name, proposal_id, _digest = self.hidden_field_proposal()

		response = self.human(self.login(USER_A), "GET", "list_second_approvals")

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assert_hidden(response.get_data(as_text=True))
		listed = [row["proposal_id"] for row in response.json["message"]["proposals"]]
		self.assertNotIn(proposal_id, listed)

	def test_refused_second_approval_does_not_show_a_field_the_person_may_not_read(self):
		name, proposal_id, digest = self.hidden_field_proposal()
		second = self.login(USER_A)

		wrong = self.approve(second, proposal_id, "0" * 64)
		frappe.db.set_value(PROPOSAL, proposal_id, "expires_at", add_to_date(now_datetime(), seconds=-5))
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		late = self.approve(second, proposal_id, digest)

		for response in (wrong, late):
			self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
			self.assert_hidden(response.get_data(as_text=True))
		self.assertEqual(self.stored(proposal_id).status, AWAITING)
		self.assertIsNone(self.stored(proposal_id).second_approver)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "internal_note"), HIDDEN_OLD)
		log = self.last_log(stage="approve", proposal=proposal_id, user=USER_A)
		self.assertEqual(log.deny_reason, "not_second_approver")

	def test_second_person_who_may_read_the_field_still_sees_and_runs_it(self):
		name, proposal_id, _digest = self.hidden_field_proposal()
		second = self.login(SECOND_MANAGER)

		row = next(row for row in self.waiting_for(second) if row["proposal_id"] == proposal_id)
		self.assertEqual(
			row["preview"]["changes"], [{"fieldname": "internal_note", "old": HIDDEN_OLD, "new": HIDDEN_NEW}]
		)
		response = self.approve(second, proposal_id, row["digest"])

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertTrue(response.json["message"]["executed"], response.json)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "internal_note"), HIDDEN_NEW)

	# --- R0, R1 and R2 stay as they were ---

	def test_r2_proposal_runs_on_the_owner_approval_alone(self):
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.propose_update(owner, name, title="Yeni")["proposal_id"]

		response = self.approve(owner, proposal_id)

		outcome = response.json["message"]
		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual(outcome["proposal"]["risk_level"], "R2")
		self.assertIsNone(outcome["proposal"]["second_approver"])
		self.assertEqual(self.title(name), "Yeni")

	def test_r2_proposal_cannot_be_approved_by_another_person(self):
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.propose_update(owner, name, title="Yeni")["proposal_id"]

		response = self.approve(self.login(MANAGER), proposal_id, self.digest_of(owner, proposal_id))

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.title(name), "Eski")
		self.assertIsNotNone(self.last_log(stage="approve", proposal=proposal_id, deny_reason="not_owner"))

	def test_r2_proposal_never_waits_in_the_second_approval_list(self):
		name = self.make_record(USER_A, title="Eski")
		owner = self.login(USER_A)
		proposal_id = self.propose_update(owner, name, title="Yeni")["proposal_id"]

		self.assertNotIn(proposal_id, [row["proposal_id"] for row in self.waiting_for(self.login(MANAGER))])

	# --- contract ---

	def test_contract_defines_the_new_status_fields_and_endpoint(self):
		import yaml

		from platform_core.ai.tests.test_registry import TestContract

		path = TestContract.CONTRACT
		if not path.exists():
			self.skipTest(f"Contract file is missing in this environment: {path}")
		contract = yaml.safe_load(path.read_text())
		schemas = contract["components"]["schemas"]

		self.assertIn(AWAITING, schemas["ProposalStatus"]["enum"])
		self.assertIn(AWAITING, contract["x-mcp-results"]["ProposalState"]["properties"]["status"]["enum"])
		for field in ("first_approved_at", "second_approver", "second_approved_at"):
			self.assertIn(field, schemas["Proposal"]["properties"])
			self.assertIn(field, schemas["Proposal"]["required"])
		for code in ("second_approver_required", "not_second_approver"):
			self.assertIn(code, schemas["DenyReason"]["enum"])
		self.assertIn("get", contract["paths"]["/platform_core.api.ai.list_second_approvals"])
