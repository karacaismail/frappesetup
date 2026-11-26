"""Revert proposal of an applied proposal (AJA-1002).

The endpoint never writes the record. It opens a new pending proposal from the stored old
values, and that proposal goes through the normal approval.
"""

import json

import frappe

from platform_core.ai.tests.base import DOCTYPE, USER_A, AiTestCase

PROPOSAL = "PLT AI Action Proposal"


class TestRevertProposal(AiTestCase):
	def applied(self, client, name: str, **data) -> str:
		"""Propose an update of the record and approve it. Return the applied proposal's id."""
		proposal_id = self.propose_update(client, name, **data)["proposal_id"]
		response = self.approve(client, proposal_id)
		self.assertEqual(response.status_code, 200, "Unexpected HTTP status")
		self.assertTrue(response.json["message"]["executed"], "Update was not executed")
		return proposal_id

	def propose_revert(self, client, proposal_id: str):
		return self.human(client, "POST", "propose_revert", body={"proposal_id": proposal_id})

	def opened(self, response) -> dict:
		self.assertEqual(response.status_code, 200, "Unexpected HTTP status")
		body = response.json["message"]
		self.assertTrue(body["opened"], "Revert proposal was not opened")
		self.assertIsNone(body["deny_reason"])
		return body["proposal"]

	def refused(self, response, code: str) -> None:
		self.assertEqual(response.status_code, 200, "Unexpected HTTP status")
		body = response.json["message"]
		self.assertFalse(body["opened"], "Revert proposal was opened")
		self.assertEqual(body["deny_reason"], code)
		self.assertIsNone(body["proposal"])

	def test_applying_stores_the_old_value_of_changed_fields_only(self):
		name = self.make_record(USER_A, title="Old", amount=10)
		client = self.login(USER_A)

		proposal_id = self.applied(client, name, title="New", amount=10)

		stored = frappe.db.get_value(PROPOSAL, proposal_id, ["revert_json", "applied_version"], as_dict=True)
		self.assertEqual(json.loads(stored.revert_json), {"title": "Old"})
		self.assertEqual(stored.applied_version, str(frappe.db.get_value(DOCTYPE, name, "modified")))

	def test_revert_opens_a_pending_proposal_and_does_not_write(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		before = frappe.db.count(PROPOSAL)

		proposal = self.opened(self.propose_revert(client, source))

		self.assertEqual(frappe.db.count(PROPOSAL), before + 1)
		self.assertEqual(proposal["status"], "pending")
		self.assertEqual(proposal["source_proposal"], source)
		self.assertEqual(proposal["tool"], "plt_update_document")
		self.assertEqual(proposal["target_name"], name)
		self.assertEqual(
			[(row["fieldname"], row["old"], row["new"]) for row in proposal["preview"]["changes"]],
			[("title", "New", "Old")],
		)
		self.assertEqual(frappe.db.get_value(PROPOSAL, proposal["proposal_id"], "source_proposal"), source)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "New")
		log = self.last_log(stage="revert", decision="allowed")
		self.assertIsNotNone(log)
		self.assertEqual(log.proposal, proposal["proposal_id"])

	def test_approving_the_revert_restores_the_old_values(self):
		name = self.make_record(USER_A, title="Old", amount=10)
		client = self.login(USER_A)
		source = self.applied(client, name, title="New", amount=25)
		proposal = self.opened(self.propose_revert(client, source))

		response = self.approve(client, proposal["proposal_id"])

		self.assertTrue(response.json["message"]["executed"], "Update was not executed")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, ["title", "amount"]), ("Old", 10))

	def test_changed_record_is_refused_with_record_changed(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		frappe.set_user(USER_A)
		doc = frappe.get_doc(DOCTYPE, name)
		doc.title = "Edited by hand"
		doc.save()
		frappe.set_user("Administrator")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		before = frappe.db.count(PROPOSAL)

		self.refused(self.propose_revert(client, source), "record_changed")

		self.assertEqual(frappe.db.count(PROPOSAL), before)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Edited by hand")
		self.assertIsNotNone(self.last_log(stage="revert", deny_reason="record_changed"))

	def test_deleted_record_is_refused_with_record_changed(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		self.drop_record(name)

		self.refused(self.propose_revert(client, source), "record_changed")

	def test_proposal_that_was_not_applied_is_refused(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		pending = self.propose_update(client, name, title="Pending")["proposal_id"]
		rejected = self.propose_update(client, name, title="Rejected")["proposal_id"]
		self.human(client, "POST", "reject_proposal", body={"proposal_id": rejected})
		failed = self.propose_update(client, name, title="Failed")["proposal_id"]
		frappe.db.set_value(PROPOSAL, failed, {"status": "consumed", "result": "failed"})
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		before = frappe.db.count(PROPOSAL)

		for proposal_id in (pending, rejected, failed):
			with self.subTest(proposal_id=proposal_id):
				self.refused(self.propose_revert(client, proposal_id), "not_applied")

		self.assertEqual(frappe.db.count(PROPOSAL), before)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_tool_without_stored_old_values_is_refused(self):
		client = self.login(USER_A)
		result = self.call_tool(
			client, "plt_create_document", {"doctype": DOCTYPE, "data": {"title": "Created"}}
		)
		self.assertFalse(result["isError"], result)
		proposal_id = result["structuredContent"]["proposal_id"]
		response = self.approve(client, proposal_id)
		self.assertTrue(response.json["message"]["executed"], "Update was not executed")
		self.addCleanup(self.drop_record, response.json["message"]["proposal"]["result_document"])

		self.refused(self.propose_revert(client, proposal_id), "not_revertable")

	def test_revert_level_is_at_least_the_source_level(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		# The source proposal was opened at a higher level than the update tool gives.
		frappe.db.set_value(PROPOSAL, source, "risk_level", "R3", update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		proposal = self.opened(self.propose_revert(client, source))

		self.assertEqual(proposal["risk_level"], "R3")
		self.assertEqual(frappe.db.get_value(PROPOSAL, proposal["proposal_id"], "risk_level"), "R3")

	def test_revert_level_keeps_the_tool_level_when_the_source_is_lower(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		frappe.db.set_value(PROPOSAL, source, "risk_level", "R1", update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		proposal = self.opened(self.propose_revert(client, source))

		self.assertEqual(proposal["risk_level"], "R2")

	def test_stored_old_values_cannot_change_after_they_are_written(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		doc = frappe.get_doc(PROPOSAL, source)
		doc.revert_json = json.dumps({"title": "Forged"})
		doc.flags.ignore_permissions = True

		with self.assertRaises(frappe.PermissionError):
			doc.save()

	def test_source_proposal_cannot_change_after_opening(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		source = self.applied(client, name, title="New")
		revert = self.opened(self.propose_revert(client, source))["proposal_id"]
		doc = frappe.get_doc(PROPOSAL, revert)
		doc.source_proposal = None
		doc.flags.ignore_permissions = True

		with self.assertRaises(frappe.PermissionError):
			doc.save()
