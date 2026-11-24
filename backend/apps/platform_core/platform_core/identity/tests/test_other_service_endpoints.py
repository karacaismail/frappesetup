"""Service token on endpoints of other modules (request from platform-core-mobil, docs/sozlesmeler.md section 7).

identity-sync calls `platform_core.api.mobile.revoke_user_installations` with its service token. The
identity hook must check this path as a service endpoint, before the mobile path rule, so the service token
is never read as a phone token. The real endpoint belongs to platform-core-mobil. When it is not installed
on this branch, a test-only stand-in is registered at the same path.
"""

import importlib
import sys
import types

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import provider_setup, service_token
from platform_core.identity.tests import helpers as h

PATH = "/api/method/platform_core.api.mobile.revoke_user_installations"
MODULE = "platform_core.api.mobile"


def _stand_in() -> dict:
	claims = service_token.require_service("identity-sync")
	return {
		"user": frappe.session.user,
		"azp": claims.get("azp"),
		"mobile_identity": bool(getattr(frappe.local, "mobile_identity", None)),
	}


class TestOtherServiceEndpoints(FrappeAPITestCase):
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
		try:
			importlib.import_module(MODULE)
			cls.stand_in = False
		except ImportError:
			if not frappe.in_test:
				raise
			module = types.ModuleType(MODULE)
			module.revoke_user_installations = _stand_in
			frappe.whitelisted.add(_stand_in)
			frappe.allowed_http_methods_for_whitelisted_func[_stand_in] = ["POST"]
			sys.modules[MODULE] = module
			cls.stand_in = True
			cls.addClassCleanup(cls._remove_stand_in, _stand_in)

	@staticmethod
	def _remove_stand_in(function):
		frappe.whitelisted.discard(function)
		frappe.allowed_http_methods_for_whitelisted_func.pop(function, None)
		sys.modules.pop(MODULE, None)

	def setUp(self):
		super().setUp()
		h.clear_links()
		h.make_link("sub-ayse", h.AYSE)

	def call(self, token: str | None):
		headers = {"Authorization": f"Bearer {token}"} if token else {}
		return h.request(h.new_client().post, PATH, json={"user": h.AYSE}, headers=headers)

	def test_path_is_a_service_endpoint(self):
		self.assertIn(PATH, service_token.SERVICE_ENDPOINTS)

	def test_identity_sync_service_token_is_accepted_as_a_service_token(self):
		response = self.call(self.key.sign(h.access_payload()))
		self.assertNotIn(
			response.json.get("exc_type") if response.is_json else None, ("ServiceTokenRejected",)
		)
		self.assertNotEqual(response.status_code, 401, response.data[:300])
		if self.stand_in:
			self.assertEqual(response.status_code, 200, response.data[:300])
			self.assertEqual(
				response.json["message"],
				{"user": "Administrator", "azp": "identity-sync", "mobile_identity": False},
			)

	def test_phone_token_is_not_accepted_on_the_service_path(self):
		phone = h.access_payload(sub="sub-ayse", azp="mobile", scope="openid mobile")
		response = self.call(self.key.sign(phone))
		self.assertEqual(response.status_code, 401, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "ServiceTokenRejected")

	def test_other_service_client_is_refused(self):
		response = self.call(self.key.sign(h.access_payload(azp="press-service")))
		self.assertIn(response.status_code, (401, 403), response.data[:300])

	def test_call_without_token_is_refused(self):
		response = self.call(None)
		self.assertIn(response.status_code, (401, 403, 404, 417), response.data[:300])
		self.assertNotEqual(response.status_code, 200)
