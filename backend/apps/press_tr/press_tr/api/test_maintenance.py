import re
from uuid import uuid4

ROUTE = "/api/method/press_tr.api.maintenance.cleanup_expired_sessions"


class MaintenanceAccessTests:
	def test_cleanup_expired_sessions_guest_denied(self):
		self.assertEqual(self.exchange("POST", ROUTE)[0], 403)

	def test_cleanup_expired_sessions_foreign_data_denied(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf}
		self.assertEqual(self.exchange("POST", ROUTE, headers)[0], 403)
