from uuid import uuid4


class LogoutAccessTests:
	def test_keycloak_backchannel_logout_guest_denied(self):
		self.assertEqual(self.post_logout("invalid-fixture"), 403)

	def test_keycloak_backchannel_logout_foreign_data_denied(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		token = self.token(
			authorized_party="press",
			sub=subject,
			iss="https://foreign.example.test",
			jti=uuid4().hex,
			events={"http://schemas.openid.net/event/backchannel-logout": {}},
		)
		self.assertEqual(self.post_logout(token), 403)
		self.assertEqual(self.exchange("GET", "/api/method/press.api.account.get", session)[0], 200)
