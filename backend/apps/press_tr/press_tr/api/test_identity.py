from uuid import uuid4

FOREIGN_ISSUER = "https://foreign.example.test"


class IdentityAccessTests:
	def test_ensure_team_guest_denied(self):
		self.assertEqual(self.call("ensure_team", self.team_payload())[0], 403)

	def test_ensure_team_foreign_data_denied(self):
		body = self.team_payload() | {"issuer": FOREIGN_ISSUER}
		self.assertEqual(self.call("ensure_team", body, self.token())[0], 403)

	def test_remove_team_member_guest_denied(self):
		body = {"issuer": self.token_issuer, "subject": "other-account", "organization_id": "other-team"}
		self.assertEqual(self.call("remove_team_member", body)[0], 403)

	def test_remove_team_member_foreign_data_denied(self):
		body = {"issuer": FOREIGN_ISSUER, "subject": "other-account", "organization_id": "other-team"}
		self.assertEqual(self.call("remove_team_member", body, self.token())[0], 403)

	def test_anonymize_user_guest_denied(self):
		self.assertEqual(
			self.call("anonymize_user", {"issuer": self.token_issuer, "subject": "other-account"})[0], 403
		)

	def test_anonymize_user_foreign_data_denied(self):
		body = {"issuer": FOREIGN_ISSUER, "subject": "other-account"}
		self.assertEqual(self.call("anonymize_user", body, self.token())[0], 403)

	def test_list_identities_guest_denied(self):
		self.assertEqual(self.identity_inventory({})[0], 403)

	def test_list_identities_foreign_data_denied(self):
		self.assertEqual(self.identity_inventory({"issuer": FOREIGN_ISSUER}, self.token())[0], 403)

	def team_payload(self):
		subject = uuid4().hex
		return {
			"issuer": self.token_issuer,
			"subject": subject,
			"email": f"{subject}@example.test",
			"email_verified": True,
			"organization_id": uuid4().hex,
		}
