"""Integration test against a live Keycloak.

The test is skipped unless these environment variables are set:
- `KIMLIK_CANLI_SITE_URL`: browser address of this site, for example http://kiraci1.localhost:8661
- `KIMLIK_CANLI_KEYCLOAK_URL`: Keycloak address, for example http://kimlik.localhost:8660
- `KIMLIK_CANLI_KULLANICI` and `KIMLIK_CANLI_PAROLA`: a fictional sample user of the realm
- `KIMLIK_CANLI_ADMIN` and `KIMLIK_CANLI_ADMIN_PAROLA`: Keycloak bootstrap admin (triggers back-channel logout)

Site settings must point at the real Keycloak. The test creates the “Social Login Key” from site settings.
"""

import html
import os
import re
import time
import unittest

import frappe
import requests
from frappe.tests import IntegrationTestCase

from platform_core.kimlik import provider_setup, site_settings
from platform_core.kimlik.tests import helpers as h

SITE_URL = os.environ.get("KIMLIK_CANLI_SITE_URL", "").rstrip("/")
KC_URL = os.environ.get("KIMLIK_CANLI_KEYCLOAK_URL", "").rstrip("/")
USER = os.environ.get("KIMLIK_CANLI_KULLANICI", "")
PASSWORD = os.environ.get("KIMLIK_CANLI_PAROLA", "")
ADMIN = os.environ.get("KIMLIK_CANLI_ADMIN", "")
ADMIN_PASSWORD = os.environ.get("KIMLIK_CANLI_ADMIN_PAROLA", "")
READY = all((SITE_URL, KC_URL, USER, PASSWORD, ADMIN, ADMIN_PASSWORD))
TIMEOUT = 20


@unittest.skipUnless(READY, "Live Keycloak environment variables are not set")
class TestLiveKeycloak(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		provider_setup.ensure_social_login_key()
		cls.register_callback_uri()
		h.ensure_user(USER)
		frappe.db.delete("Platform Identity Link", {"issuer": site_settings.issuer()})
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("Platform Identity Link", {"issuer": site_settings.issuer()})
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def register_callback_uri(cls):
		"""The development realm still registers Frappe's old callback (kimlik-realm owns the realm file).
		Until it is updated, the own callback is added to the client of this disposable Keycloak."""
		token = requests.post(
			f"{KC_URL}/realms/master/protocol/openid-connect/token",
			data={
				"grant_type": "password",
				"client_id": "admin-cli",
				"username": ADMIN,
				"password": ADMIN_PASSWORD,
			},
			timeout=TIMEOUT,
		).json()["access_token"]
		headers = {"Authorization": f"Bearer {token}"}
		clients = requests.get(
			f"{KC_URL}/admin/realms/platform/clients",
			params={"clientId": site_settings.get().client_id},
			headers=headers,
			timeout=TIMEOUT,
		).json()
		client = clients[0]
		callback = f"{SITE_URL}/api/method/platform_core.api.auth.keycloak_callback"
		if callback not in client.get("redirectUris", []):
			client["redirectUris"] = [*client.get("redirectUris", []), callback]
			requests.put(
				f"{KC_URL}/admin/realms/platform/clients/{client['id']}",
				json=client,
				headers=headers,
				timeout=TIMEOUT,
			).raise_for_status()

	def sign_in_through_keycloak(self) -> requests.Session:
		browser = requests.Session()
		response = browser.post(
			f"{SITE_URL}/api/method/platform_core.api.auth.get_login_url",
			json={"redirect_to": "/panel"},
			timeout=TIMEOUT,
		)
		self.assertEqual(response.status_code, 200, response.text[:300])
		login_url = response.json()["message"]["login_url"]
		self.assertTrue(login_url.startswith(f"{KC_URL}/realms/platform/protocol/openid-connect/auth?"))

		page = browser.get(login_url, timeout=TIMEOUT)
		self.assertEqual(page.status_code, 200, page.text[:300])
		# Keycloak 26 treats *.localhost as a secure context and sets Secure cookies even over http.
		# Browsers send them to http://*.localhost; the requests cookie jar does not, so the flag is dropped.
		for cookie in browser.cookies:
			cookie.secure = False
		match = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', page.text)
		self.assertIsNotNone(match, "Keycloak login form not found")
		form_action = html.unescape(match.group(1))

		callback = browser.post(
			form_action,
			data={"username": USER, "password": PASSWORD, "credentialId": ""},
			allow_redirects=False,
			timeout=TIMEOUT,
		)
		self.assertEqual(callback.status_code, 302, callback.text[:300])
		location = callback.headers["Location"]
		self.assertTrue(
			location.startswith(f"{SITE_URL}/api/method/platform_core.api.auth.keycloak_callback?")
		)

		site = browser.get(location, allow_redirects=False, timeout=TIMEOUT)
		self.assertEqual(site.status_code, 302, site.text[:300])
		self.assertTrue(site.headers["Location"].endswith("/panel"))
		return browser

	def csrf_token(self, browser) -> str:
		frappe.db.commit()
		sessions = frappe.qb.DocType("Sessions")
		rows = (
			frappe.qb.from_(sessions)
			.select(sessions.sessiondata)
			.where(sessions.sid == browser.cookies.get("sid"))
			.run()
		)
		self.assertTrue(rows, "session record not found")
		return frappe.parse_json(rows[0][0] or "{}").get("csrf_token") or ""

	def logged_user(self, browser) -> str:
		response = browser.get(f"{SITE_URL}/api/method/frappe.auth.get_logged_user", timeout=TIMEOUT)
		body = response.json()
		if response.status_code in (401, 403) and body.get("exc_type") in (
			"PermissionError",
			"SessionExpired",
		):
			return "Guest"
		self.assertEqual(response.status_code, 200, response.text[:300])
		return body["message"]

	def admin_token(self) -> str:
		response = requests.post(
			f"{KC_URL}/realms/master/protocol/openid-connect/token",
			data={
				"grant_type": "password",
				"client_id": "admin-cli",
				"username": ADMIN,
				"password": ADMIN_PASSWORD,
			},
			timeout=TIMEOUT,
		)
		self.assertEqual(response.status_code, 200, response.text[:300])
		return response.json()["access_token"]

	def test_sign_in_creates_link_and_back_channel_logout_closes_session(self):
		browser = self.sign_in_through_keycloak()
		self.assertEqual(self.logged_user(browser), USER)
		frappe.db.commit()
		link = frappe.db.get_value(
			"Platform Identity Link",
			{"issuer": site_settings.issuer(), "user": USER},
			["subject"],
			as_dict=True,
		)
		self.assertTrue(link and link.subject, "identity link was not created")

		headers = {"Authorization": f"Bearer {self.admin_token()}"}
		users = requests.get(
			f"{KC_URL}/admin/realms/platform/users",
			params={"email": USER, "exact": "true"},
			headers=headers,
			timeout=TIMEOUT,
		).json()
		self.assertEqual(len(users), 1)
		self.assertEqual(users[0]["id"], link.subject, "the linked sub must be the Keycloak user id")

		logout = requests.post(
			f"{KC_URL}/admin/realms/platform/users/{link.subject}/logout", headers=headers, timeout=TIMEOUT
		)
		self.assertEqual(logout.status_code, 204, logout.text[:300])

		last = None
		for _ in range(10):
			last = self.logged_user(browser)
			if last == "Guest":
				break
			time.sleep(1)
		self.assertEqual(last, "Guest", "back-channel logout did not close the Frappe session")

	def test_logout_endpoint_returns_keycloak_logout_url(self):
		browser = self.sign_in_through_keycloak()
		response = browser.post(
			f"{SITE_URL}/api/method/platform_core.api.auth.logout",
			headers={"X-Frappe-CSRF-Token": self.csrf_token(browser)},
			timeout=TIMEOUT,
		)
		self.assertEqual(response.status_code, 200, response.text[:300])
		url = response.json()["message"]["logout_url"]
		self.assertTrue(url.startswith(f"{KC_URL}/realms/platform/protocol/openid-connect/logout?"))
		self.assertEqual(self.logged_user(browser), "Guest")
		# Keycloak either shows its logout page or redirects to post_logout_redirect_uri (/panel is another task's page).
		page = browser.get(url, allow_redirects=False, timeout=TIMEOUT)
		self.assertIn(page.status_code, (200, 302), page.text[:300])
		if page.status_code == 302:
			self.assertTrue(page.headers["Location"].startswith(site_settings.get().panel_url))
