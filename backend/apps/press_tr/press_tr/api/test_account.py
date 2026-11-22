import re
from uuid import uuid4

ROUTE = "/api/method/press_tr.api.account.request_deletion"


class AccountAccessTests:
	def test_request_deletion_guest_denied(self):
		headers = {"Content-Type": "application/json"}
		self.assertEqual(self.exchange("POST", ROUTE, headers, '{"confirm":false}')[0], 403)

	def test_request_deletion_foreign_data_denied(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		self.assertEqual(
			self.exchange("POST", ROUTE, headers, '{"confirm":false,"subject":"other-account"}')[0], 403
		)
