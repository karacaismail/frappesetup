"""Permission tests of the AI endpoints, one pair per endpoint, as the security gate asks.

`*_guest_denied`: a request without credentials cannot use the endpoint.
`*_foreign_data_denied`: a signed-in user cannot reach another user's protected data through it.
Requests go through Frappe's WSGI application, so authentication runs on the real path.
"""

import frappe

from platform_core.yapay_zeka.tests.base import DOCTYPE, USER_A, USER_B, YzTestCase


class TestAiEndpoints(YzTestCase):
	def guest(self, method: str, endpoint: str, body=None, query=None):
		"""Send the request without credentials and return the status code."""
		return self.human(self.anonymous(), method, endpoint, body=body, query=query).status_code

	def proposal_of_a(self) -> tuple[str, str, str]:
		"""Open a proposal as user A. Return the record, the proposal id and its digest."""
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]
		return name, proposal_id, self.digest_of(client, proposal_id)

	def status_of(self, proposal_id: str) -> tuple:
		return tuple(frappe.db.get_value("AI Action Proposal", proposal_id, ["status", "result"]))

	# --- mcp ---

	def test_mcp_guest_denied(self):
		response = self.rpc(self.anonymous(), "tools/list")

		self.assertEqual(response.status_code, 403)
		self.assertNotIn("tools", response.get_data(as_text=True))

	def test_mcp_foreign_data_denied(self):
		name = self.make_record(USER_A, title="Private to A")

		result = self.call_tool(self.login(USER_B), "get_document", {"doctype": DOCTYPE, "name": name})

		self.assert_denied(result, "permission")
		self.assertNotIn("Private to A", result["content"][0]["text"])

	# --- issue_agent_token ---

	def test_issue_agent_token_guest_denied(self):
		self.assertEqual(self.guest("POST", "issue_agent_token", body={}), 403)

	def test_issue_agent_token_foreign_data_denied(self):
		name = self.make_record(USER_A, title="Private to A")
		token = self.issue_token(self.login(USER_B))

		result = self.call_tool(
			self.anonymous(), "get_document", {"doctype": DOCTYPE, "name": name}, token=token
		)

		self.assert_denied(result, "permission")

	# --- list_proposals ---

	def test_list_proposals_guest_denied(self):
		self.assertEqual(self.guest("GET", "list_proposals"), 403)

	def test_list_proposals_foreign_data_denied(self):
		_name, proposal_id, _digest = self.proposal_of_a()

		listed = self.human(self.login(USER_B), "GET", "list_proposals", query={"limit": 100}).json["message"]

		self.assertNotIn(proposal_id, [row["proposal_id"] for row in listed])

	# --- get_proposal ---

	def test_get_proposal_guest_denied(self):
		_name, proposal_id, _digest = self.proposal_of_a()

		self.assertEqual(self.guest("GET", "get_proposal", query={"proposal_id": proposal_id}), 403)

	def test_get_proposal_foreign_data_denied(self):
		_name, proposal_id, digest = self.proposal_of_a()

		response = self.human(self.login(USER_B), "GET", "get_proposal", query={"proposal_id": proposal_id})

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(digest, response.get_data(as_text=True))

	# --- approve_proposal ---

	def test_approve_proposal_guest_denied(self):
		name, proposal_id, digest = self.proposal_of_a()

		status = self.guest("POST", "approve_proposal", body={"proposal_id": proposal_id, "digest": digest})

		self.assertEqual(status, 403)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_approve_proposal_foreign_data_denied(self):
		name, proposal_id, digest = self.proposal_of_a()

		response = self.approve(self.login(USER_B), proposal_id, digest)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")
		self.assertEqual(self.status_of(proposal_id)[0], "pending")

	# --- reject_proposal ---

	def test_reject_proposal_guest_denied(self):
		_name, proposal_id, _digest = self.proposal_of_a()

		self.assertEqual(self.guest("POST", "reject_proposal", body={"proposal_id": proposal_id}), 403)
		self.assertEqual(self.status_of(proposal_id)[0], "pending")

	def test_reject_proposal_foreign_data_denied(self):
		_name, proposal_id, _digest = self.proposal_of_a()

		response = self.human(
			self.login(USER_B), "POST", "reject_proposal", body={"proposal_id": proposal_id}
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.status_of(proposal_id)[0], "pending")

	# --- resolve_proposal ---

	def unknown_proposal_of_a(self) -> str:
		_name, proposal_id, _digest = self.proposal_of_a()
		frappe.db.set_value("AI Action Proposal", proposal_id, {"status": "consumed", "result": "unknown"})
		return proposal_id

	def test_resolve_proposal_guest_denied(self):
		proposal_id = self.unknown_proposal_of_a()

		status = self.guest(
			"POST", "resolve_proposal", body={"proposal_id": proposal_id, "outcome": "failed"}
		)

		self.assertEqual(status, 403)
		self.assertEqual(self.status_of(proposal_id), ("consumed", "unknown"))

	def test_resolve_proposal_foreign_data_denied(self):
		proposal_id = self.unknown_proposal_of_a()
		body = {"proposal_id": proposal_id, "outcome": "failed"}

		response = self.human(self.login(USER_B), "POST", "resolve_proposal", body=body)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.status_of(proposal_id), ("consumed", "unknown"))

	# --- purge_logs ---

	def test_purge_logs_guest_denied(self):
		before = frappe.db.count("AI Action Log")

		self.assertEqual(self.guest("POST", "purge_logs", body={"dry_run": False}), 403)
		self.assertEqual(frappe.db.count("AI Action Log"), before)

	def test_purge_logs_foreign_data_denied(self):
		"""The log holds every user's actions. A user without the admin role cannot delete or count it."""
		before = frappe.db.count("AI Action Log")

		response = self.human(self.login(USER_A), "POST", "purge_logs", body={"dry_run": False})

		self.assertEqual(response.status_code, 403)
		self.assertNotIn("logs", response.get_data(as_text=True))
		self.assertGreaterEqual(frappe.db.count("AI Action Log"), before)
