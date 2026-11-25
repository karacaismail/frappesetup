"""G-163 sentence 12: "sign out all devices" closes the phone session at once.

Keycloak ends every session of the user. It sends one back-channel logout token per client of each
session. The phone client (`mobile-app`) has its own token: `aud` is the phone client, `sid` is the
phone session. Before this change Frappe refused that audience, so the phone kept its access token
for up to 300 seconds. Now the same endpoint accepts it and denies the phone session at once.
A phone token never closes the web sessions of the user.
"""

import time
from types import SimpleNamespace
from uuid import uuid4

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.api.mobile import _register
from platform_core.identity import provider_setup
from platform_core.identity.tests import helpers as h
from platform_core.mobile.protocol import MobileError
from platform_core.mobile.sessions import is_session_revoked, require_active_session
from platform_core.mobile.store import MobileStore

ENDPOINT = "/api/method/platform_core.api.keycloak_backchannel_logout"
MOBILE_CLIENT = "mobile-app"
WEB_SID = "11111111-1111-4111-8111-111111111111"


class TestMobileBackChannelLogout(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings({"kimlik_mobil_azp": [MOBILE_CLIENT]}).__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		for email in h.SAMPLE_USERS:
			h.ensure_user(email)
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def setUp(self):
		super().setUp()
		h.clear_links()
		self.installations = []

	def tearDown(self):
		for name in self.installations:
			frappe.db.delete("PLT Mobile Installation", {"name": name})
		frappe.db.commit()  # nosemgrep: the HTTP requests of this test commit their own data
		super().tearDown()

	def phone(self, account=h.AYSE, subject="sub-ayse"):
		installation = str(uuid4())
		identity = SimpleNamespace(
			account=account,
			site=frappe.local.site,
			scope="mobile",
			principal="fixture",
			issued_at=int(time.time()),
			sid=str(uuid4()),
			subject=subject,
			installation=installation,
			auth_time=int(time.time()),
		)
		_register(identity, {"installation_id": installation})
		frappe.db.commit()  # nosemgrep: the logout request runs in its own transaction
		self.installations.append(installation)
		return identity

	def send(self, payload):
		client = h.new_client()
		return h.request(
			client.post,
			ENDPOINT,
			data={"logout_token": self.key.sign(payload)},
			content_type="application/x-www-form-urlencoded",
			headers=h.csrf_headers(client),
		)

	def assert_phone_denied(self, identity):
		frappe.db.rollback()
		self.assertTrue(is_session_revoked(identity.sid))
		with self.assertRaises(MobileError) as raised:
			require_active_session(identity.sid)
		self.assertEqual(raised.exception.code, "mobile_session_revoked")
		self.assertTrue(frappe.db.get_value("PLT Mobile Installation", identity.installation, "revoked"))
		with self.assertRaises(MobileError):
			MobileStore().require_installation(identity, identity.installation)

	def test_signing_out_every_device_denies_the_phone_session_at_once(self):
		web = h.new_client()
		h.login_with_keycloak(web, h.userinfo("sub-ayse", h.AYSE, sid=WEB_SID))
		phone = self.phone()
		other_user_phone = self.phone(h.MEHMET, "sub-mehmet")
		started = time.monotonic()
		for payload in (
			h.logout_payload(sub="sub-ayse", sid=WEB_SID),
			h.logout_payload(aud=MOBILE_CLIENT, sub="sub-ayse", sid=phone.sid),
		):
			response = self.send(payload)
			self.assertEqual(response.status_code, 200, response.data[:300])
			self.assertEqual(response.json["message"], {"closed_sessions": 1})
		# No waiting for the 300 second access token lifetime: the next phone request is refused.
		self.assertLess(time.monotonic() - started, 300)
		self.assert_phone_denied(phone)
		self.assertEqual(h.logged_user(web), "Guest")
		self.assertFalse(is_session_revoked(other_user_phone.sid))
		MobileStore().require_installation(other_user_phone, other_user_phone.installation)

	def test_phone_token_closes_only_the_phone(self):
		web = h.new_client()
		h.login_with_keycloak(web, h.userinfo("sub-ayse", h.AYSE, sid=WEB_SID))
		phone = self.phone()
		other_phone = self.phone()
		response = self.send(h.logout_payload(aud=MOBILE_CLIENT, sub="sub-ayse", sid=phone.sid))
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"closed_sessions": 1})
		self.assert_phone_denied(phone)
		# The web session has another sid. A phone token must not close it through the subject.
		self.assertEqual(h.logged_user(web), h.AYSE)
		self.assertFalse(is_session_revoked(other_phone.sid))

	def test_phone_session_without_installation_is_still_denied(self):
		sid = str(uuid4())
		response = self.send(h.logout_payload(aud=MOBILE_CLIENT, sub="sub-ayse", sid=sid))
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"closed_sessions": 0})
		frappe.db.rollback()
		self.assertTrue(is_session_revoked(sid))

	def test_audience_outside_the_mobile_list_is_rejected(self):
		phone = self.phone()
		for audience in ("press", "mobile"):
			with self.subTest(audience):
				response = self.send(h.logout_payload(aud=audience, sub="sub-ayse", sid=phone.sid))
				self.assertEqual(response.status_code, 400, response.data[:300])
		frappe.db.rollback()
		self.assertFalse(is_session_revoked(phone.sid))
