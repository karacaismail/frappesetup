import json
from uuid import uuid4

LOGIN_ROUTE = "/api/method/press_tr.api.auth.get_login_url"
CALLBACK_ROUTE = "/api/method/press_tr.api.auth.keycloak_callback"


class AuthAccessTests:
	def test_get_login_url_guest_denied(self):
		# Guests may initiate login, but cannot use the endpoint with the wrong verb.
		self.assertEqual(self.exchange("GET", LOGIN_ROUTE)[0], 403)

	def test_get_login_url_foreign_data_denied(self):
		headers = {"Content-Type": "application/json"}
		body = json.dumps({"reauthentication": {"subject": "other-account"}})
		self.assertEqual(self.exchange("POST", LOGIN_ROUTE, headers, body)[0], 403)

	def test_keycloak_callback_guest_denied(self):
		self.assertEqual(self.exchange("GET", CALLBACK_ROUTE)[0], 403)

	def test_keycloak_callback_foreign_data_denied(self):
		_login_url, other_browser = self.start_login()
		subject = uuid4().hex
		self.sign_in(subject, f"{subject}@example.test", uuid4().hex, other_browser=other_browser)
