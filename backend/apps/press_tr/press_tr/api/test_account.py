import re
from uuid import uuid4

ROUTE = "/api/method/press_tr.api.account.request_deletion"
RECOVERY_ROUTE = "/api/method/press_tr.api.account.request_recovery"
KEY_REMOVAL_ROUTE = "/api/method/press_tr.api.account.remove_recovered_keys"


class AccountAccessTests:
	def test_request_deletion_guest_denied(self):
		headers = {"Content-Type": "application/json"}
		self.assertEqual(self.exchange("POST", ROUTE, headers, '{"confirm":false}')[0], 403)

	def test_request_deletion_foreign_data_denied(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		self.assertEqual(
			self.exchange("POST", ROUTE, headers, '{"confirm":false,"subject":"other-account"}')[0], 403
		)

	def test_request_recovery_guest_denied(self):
		# Guests may ask for recovery, but only with POST.
		self.assertEqual(self.exchange("GET", f"{RECOVERY_ROUTE}?email=customer@example.test")[0], 403)

	def test_request_recovery_foreign_data_denied(self):
		# The request accepts only an address. It cannot name another account's identity record.
		headers = {"Content-Type": "application/json"}
		body = '{"email":"customer@example.test","identity_link":"other-account"}'
		self.assertEqual(self.exchange("POST", RECOVERY_ROUTE, headers, body)[0], 403)

	def test_remove_recovered_keys_guest_denied(self):
		# AJA-420: only a signed-in reviewer may start the key removal.
		headers = {"Content-Type": "application/json"}
		self.assertEqual(self.exchange("POST", KEY_REMOVAL_ROUTE, headers, '{"review":"a1b2c3d4e5"}')[0], 403)

	def test_remove_recovered_keys_foreign_data_denied(self):
		# A customer has no write permission on recovery reviews, so no record name opens the step.
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		self.assertEqual(self.exchange("POST", KEY_REMOVAL_ROUTE, headers, '{"review":"a1b2c3d4e5"}')[0], 403)
