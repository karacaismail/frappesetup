import json
import re
from urllib.parse import urlencode
from uuid import uuid4

REVISION_ROUTE = "/api/method/press_tr.pricing.create_price_revision"
PANEL_PLANS_ROUTE = "/api/method/press.api.site.get_site_plans"


class PricingAccessTests:
	def test_create_price_revision_guest_denied(self):
		self.assertEqual(self.exchange("POST", REVISION_ROUTE)[0], 403)

	def test_create_price_revision_foreign_data_denied(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		payload = {
			"plan": "other-plan",
			"name": "revised-plan",
			"price_try": "100",
			"price_usd": "5",
			"effective_date": "2099-01-01",
		}
		self.assertEqual(self.exchange("POST", REVISION_ROUTE, headers, json.dumps(payload))[0], 403)

	def test_get_panel_plans_guest_denied(self):
		self.assertEqual(self.exchange("GET", PANEL_PLANS_ROUTE)[0], 403)

	def test_get_panel_plans_foreign_data_denied(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _headers, baseline = self.exchange("GET", PANEL_PLANS_ROUTE, session)
		self.assertEqual(status, 200)
		params = urlencode({"filters": json.dumps({"name": "other-plan"})})
		status, _headers, attempted = self.exchange("GET", f"{PANEL_PLANS_ROUTE}?{params}", session)
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(attempted)["message"], json.loads(baseline)["message"])
