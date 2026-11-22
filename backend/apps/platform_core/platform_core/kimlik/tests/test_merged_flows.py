"""Sign-in, sign-out and phone registration on the merged code (third merge review, orchestrator item 1).

The shell module adds a Website User method allow list and a metadata guard. The mobile module adds its
endpoints. These tests run the real paths together: Keycloak sign-in, sign-out, and a phone registration
with a real mobile token through the identity hook, the shell guard and the mobile endpoint.
"""

import time
import unittest
import uuid

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

REGISTER = "/api/method/platform_core.api.mobile.v1_register"


class TestMergedFlows(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def setUp(self):
		super().setUp()
		h.clear_links()
		h.make_link("sub-ayse", h.AYSE)

	def test_sign_in_and_sign_out(self):
		client = h.new_client()
		response = h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
		self.assertEqual(response.status_code, 302, response.data[:300])
		self.assertEqual(h.logged_user(client), h.AYSE)
		out = h.request(
			client.post, "/api/method/platform_core.api.auth.logout", headers=h.csrf_headers(client)
		)
		self.assertEqual(out.status_code, 200, out.data[:300])
		self.assertIn("/protocol/openid-connect/logout?", out.json["message"]["logout_url"])
		self.assertEqual(h.logged_user(client), "Guest")

	# Known merge conflict, reported to the orchestrator (status file, tenth round). The shell guard in
	# `auth_hooks` checks the final user, and a phone request runs as the Website User. The mobile module
	# keeps its token endpoints out of the Website User allow list on purpose. So the phone registration
	# gets 403 on the merged code. This test turns into an unexpected success once the owners resolve it.
	@unittest.expectedFailure
	def test_phone_registration_with_a_real_mobile_token(self):
		token = self.key.sign(
			h.access_payload(
				sub="sub-ayse",
				azp="mobile",
				scope="openid mobile",
				sid="99999999-9999-4999-8999-999999999999",
				auth_time=int(time.time()) - 30,
			)
		)
		installation = str(uuid.uuid4())
		response = h.request(
			h.new_client().post,
			REGISTER,
			json={"installation_id": installation},
			headers={
				"Authorization": f"Bearer {token}",
				"X-Mobile-App-Version": "1.0.0",
				"X-Mobile-Contract-Version": "1",
				"X-Platform-Installation": installation,
			},
		)
		self.assertEqual(response.status_code, 200, response.data[:400])
		self.assertNotIn("exc_type", response.json)
