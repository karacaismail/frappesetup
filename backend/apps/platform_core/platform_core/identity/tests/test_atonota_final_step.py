"""The final step of an action checks again with `Policy.confirm` (G-161, AJA-230).

Expected rules, from G-161 and the architecture note of AJA-213:
- a "ready" result holds for one action only; the final step checks again right before the write,
- if the evidence is gone at the final check, the write does not run,
- if the policy changed between the two checks, the write does not run,
- the evidence comes from Frappe records; roles are not evidence.

The test policy below holds no price. It has one action that needs membership only.
"""

from unittest.mock import patch

import frappe
from atonota_login import decision
from frappe.tests import IntegrationTestCase

from platform_core.identity.atonota import decision_api
from platform_core.identity.tests import helpers as h

MEMBER = "atonota.final.member@example.test"
ROLE_ONLY = "atonota.final.role@example.test"
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
		h.ensure_user(ROLE_ONLY, user_type="Website User", roles=["System Manager"])
		frappe.db.set_value("User", ROLE_ONLY, "user_type", "Website User")

	def setUp(self):
		super().setUp()
		# Frappe derives the user type from desk roles when a user is saved. The test sets the record directly.
		frappe.db.set_value("User", MEMBER, "user_type", "System User")
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

	def test_roles_are_not_evidence(self):
		# A role does not make a portal user a member. Roles from a token are never read.
		evidence = decision_api.collect_evidence(ROLE_ONLY, decision_api.now_utc())
		self.assertNotIn("membership", evidence)
		frappe.set_user(ROLE_ONLY)
		with self.assertRaises(decision_api.ActionRefused):
			decision_api.run_final_step(ACTION, self.work)
		self.assertEqual(self.calls, [])

	def test_disabled_user_has_no_evidence(self):
		frappe.db.set_value("User", MEMBER, "enabled", 0)
		try:
			self.assertEqual(decision_api.collect_evidence(MEMBER, decision_api.now_utc()), {})
		finally:
			frappe.db.set_value("User", MEMBER, "enabled", 1)
