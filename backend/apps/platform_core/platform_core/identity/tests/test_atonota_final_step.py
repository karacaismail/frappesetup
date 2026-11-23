"""The final step of an action checks again with `Policy.confirm` (G-161, AJA-230).

Expected rules, from G-161 and the architecture note of AJA-213:
- a "ready" result holds for one action only; the final step checks again right before the write,
- if the evidence is gone at the final check, the write does not run,
- if the policy changed between the two checks, the write does not run,
- the evidence comes from Frappe records; roles from a token or the request are not read,
- the final step refuses to start while the transaction holds earlier writes, so its commit of the
  owner task never makes a caller's pending write permanent (AJA-264).

Membership is the Frappe user type for now. Frappe derives "System User" from desk roles when a
user is saved, so a desk role on the server record does make membership evidence. This is a known
debt until the organisation membership record exists (G-160, PROJECT-RECORD.md).

The test policy below holds no price. It has one action that needs membership only.
"""

from unittest.mock import patch

import frappe
from atonota_login import decision
from frappe.tests import IntegrationTestCase

from platform_core.identity.atonota import decision_api
from platform_core.identity.tests import helpers as h

MEMBER = "atonota.final.member@example.test"
DESK_ROLE = "atonota.final.role@example.test"
WRITE_MARK = "[AtonotA final step pending write]"
ACTION = "example-final-step"


def policy(description: str = "Example final step.") -> decision.Policy:
	return decision.Policy(
		{
			"rules": [],
			"actions": [
				{
					"id": ACTION,
					"description": description,
					"controls": [
						{
							"id": "membership",
							"applies": True,
							"required": True,
							"evidence": "membership",
							"rules": [],
						}
					],
				}
			],
		}
	)


class TestAtonotaFinalStep(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.ensure_user(MEMBER, user_type="System User")
		h.ensure_user(DESK_ROLE, user_type="Website User")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def setUp(self):
		super().setUp()
		# Frappe derives the user type from desk roles when a user is saved. The test sets the record directly.
		frappe.db.set_value("User", MEMBER, "user_type", "System User")
		# The final step refuses pending writes. The fixture write above is committed first.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		self.calls = []
		loader = patch.object(decision_api, "_load_policy", return_value=policy())
		self.loader = loader.start()
		self.addCleanup(loader.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def work(self):
		self.calls.append(frappe.session.user)
		return {"done": True}

	def test_work_runs_once_after_the_final_check(self):
		frappe.set_user(MEMBER)
		self.assertEqual(decision_api.run_final_step(ACTION, self.work), {"done": True})
		self.assertEqual(self.calls, [MEMBER])

	def test_final_check_calls_confirm_with_fresh_evidence(self):
		frappe.set_user(MEMBER)
		with patch.object(
			decision.Policy, "confirm", autospec=True, side_effect=decision.Policy.confirm
		) as confirm:
			decision_api.run_final_step(ACTION, self.work)
		self.assertEqual(confirm.call_count, 1)
		earlier = confirm.call_args.args[1]
		self.assertEqual((earlier.status, earlier.action), (decision.READY, ACTION))

	def test_lost_evidence_before_the_write_stops_the_work(self):
		frappe.set_user(MEMBER)
		valid = decision_api.collect_evidence(MEMBER, decision_api.now_utc())
		with patch.object(decision_api, "collect_evidence", side_effect=[valid, {}]):
			with self.assertRaises(decision_api.ActionRefused) as refused:
				decision_api.run_final_step(ACTION, self.work)
		self.assertIn("denied", str(refused.exception))
		self.assertEqual(self.calls, [])

	def test_policy_change_between_the_checks_stops_the_work(self):
		frappe.set_user(MEMBER)
		self.loader.side_effect = [policy(), policy("Changed description.")]
		with self.assertRaises(decision_api.ActionRefused) as refused:
			decision_api.run_final_step(ACTION, self.work)
		self.assertIn("policy-changed", str(refused.exception))
		self.assertEqual(self.calls, [])

	def test_guest_cannot_run_a_final_step(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			decision_api.run_final_step(ACTION, self.work)
		self.assertEqual(self.calls, [])

	def test_desk_role_on_the_server_record_makes_membership_evidence(self):
		# Known debt (G-160): membership is read from `user_type`, and Frappe derives it from desk roles.
		user = frappe.get_doc("User", DESK_ROLE)
		user.remove_roles("System Manager")
		self.assertEqual(frappe.db.get_value("User", DESK_ROLE, "user_type"), "Website User")
		self.assertNotIn("membership", decision_api.collect_evidence(DESK_ROLE, decision_api.now_utc()))
		frappe.get_doc("User", DESK_ROLE).add_roles("System Manager")
		self.assertEqual(frappe.db.get_value("User", DESK_ROLE, "user_type"), "System User")
		self.assertIn("membership", decision_api.collect_evidence(DESK_ROLE, decision_api.now_utc()))
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		frappe.set_user(DESK_ROLE)
		self.assertEqual(decision_api.run_final_step(ACTION, self.work), {"done": True})
		self.assertEqual(self.calls, [DESK_ROLE])

	def test_token_roles_are_not_read(self):
		# Only the server record counts. A role claim in the session data changes nothing.
		frappe.set_user(DESK_ROLE)
		frappe.get_doc("User", DESK_ROLE).remove_roles("System Manager")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		frappe.session.data["roles"] = ["System Manager"]
		with self.assertRaises(decision_api.ActionRefused):
			decision_api.run_final_step(ACTION, self.work)
		self.assertEqual(self.calls, [])

	def test_pending_write_stops_the_final_step_before_any_decision(self):
		# The real policy leaves "open-paid-plan" in configuration_required. That path commits the
		# owner task. A write made earlier in the request must not become permanent with it.
		self.loader.return_value = decision.load_policy()
		mark = f"{WRITE_MARK} {frappe.generate_hash(length=10)}"
		frappe.db.savepoint("atonota_pending")
		frappe.get_doc({"doctype": "ToDo", "status": "Open", "description": mark}).insert(
			ignore_permissions=True
		)
		frappe.set_user(MEMBER)
		with (
			patch.object(frappe.db, "commit") as commit,
			patch.object(decision_api, "_judge", wraps=decision_api._judge) as judge,
		):
			with self.assertRaises(decision_api.PendingWrites):
				decision_api.run_final_step("open-paid-plan", self.work)
		commit.assert_not_called()
		judge.assert_not_called()
		self.assertEqual(self.calls, [])
		frappe.db.rollback(save_point="atonota_pending")
		self.assertFalse(frappe.db.exists("ToDo", {"description": mark}))

	def test_disabled_user_has_no_evidence(self):
		frappe.db.set_value("User", MEMBER, "enabled", 0)
		try:
			self.assertEqual(decision_api.collect_evidence(MEMBER, decision_api.now_utc()), {})
		finally:
			frappe.db.set_value("User", MEMBER, "enabled", 1)
