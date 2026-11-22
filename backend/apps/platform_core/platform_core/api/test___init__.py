"""HTTP access checks for the back-channel sign-out endpoint."""

from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik.tests import helpers as h

ENDPOINT = "/api/method/platform_core.api.keycloak_backchannel_logout"


class TestBackChannelAccess(FrappeAPITestCase):
	def test_keycloak_backchannel_logout_guest_denied(self):
		response = h.request(h.new_client().post, ENDPOINT)
		self.assertEqual(response.status_code, 400)
		self.assertNotIn("message", response.json)

	def test_keycloak_backchannel_logout_foreign_data_denied(self):
		key = h.key()
		with h.SiteSettings(), h.jwks_patch(key):
			response = h.request(
				h.new_client().post,
				ENDPOINT,
				data={"logout_token": key.sign(h.logout_payload(aud="other-tenant"))},
			)
		self.assertEqual(response.status_code, 400)
		self.assertNotIn("message", response.json)
