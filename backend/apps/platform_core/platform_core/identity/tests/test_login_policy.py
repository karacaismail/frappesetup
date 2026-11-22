"""AU-19 (Keycloak-only sign-in) and A-7 (portal pages closed) tests."""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import login_policy, provider_setup
from platform_core.identity.tests import helpers as h


class TestKeycloakOnly(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		cls.admin_password = frappe.generate_hash(length=24)
		cls.admin_user = h.ensure_system_manager("kimlik.yonetici@example.test", cls.admin_password)
		h.refresh()
		cls.patcher = h.jwks_patch()
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	@classmethod
	def tearDownClass(cls):
		h.clear_links()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		h.clear_links()

	def password_login(self):
		return h.request(
			h.new_client().post,
			"/api/method/login",
			data={"usr": self.admin_user, "pwd": self.admin_password},
		)

	def test_password_login_works_while_gate_is_off(self):
		response = self.password_login()
		self.assertEqual(response.status_code, 200, response.data[:200])

	def test_gate_on_rejects_password_and_email_link_but_keycloak_works(self):
		with h.SiteSettings({"identity_keycloak_only": 1}):
			password = self.password_login()
			self.assertEqual(password.status_code, 401, password.data[:200])

			with h.single_value("System Settings", "login_with_email_link", 1):
				link = h.request(
					h.new_client().post,
					"/api/method/frappe.www.login.send_login_link",
					data={"email": h.AYSE},
				)
				self.assertEqual(link.status_code, 403)
				key = h.request(
					h.new_client().get,
					"/api/method/frappe.www.login.login_via_key",
					query_string={"key": "x"},
				)
				self.assertEqual(key.status_code, 403)

			client = h.new_client()
			response = h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
			self.assertEqual(response.status_code, 302)
			self.assertEqual(h.logged_user(client), h.AYSE)

	def test_gate_covers_every_local_login_function_and_api_shape(self):
		# E2 in the security review: the gate applies to the function, not to one URL spelling.
		with h.SiteSettings({"identity_keycloak_only": 1}):
			for path in (
				"/api/method/frappe.www.login.send_login_link",
				"/api/v1/method/frappe.www.login.send_login_link",
				"/api/v2/method/frappe.www.login.send_login_link",
			):
				response = h.request(h.new_client().post, path, data={"email": h.AYSE})
				self.assertEqual(response.status_code, 403, f"{path}: {response.status_code}")
			via_cmd = h.request(
				h.new_client().post, "/", data={"cmd": "frappe.www.login.send_login_link", "email": h.AYSE}
			)
			self.assertEqual(via_cmd.status_code, 403, via_cmd.data[:200])
			via_get_cmd = h.request(
				h.new_client().get, "/", query_string={"cmd": "frappe.www.login.login_via_key", "key": "x"}
			)
			self.assertEqual(via_get_cmd.status_code, 403, via_get_cmd.data[:200])
			for method, path, body in (
				(
					"post",
					"/api/method/frappe.core.doctype.user.user.update_password",
					{"key": "x", "new_password": "A-long-password-123"},
				),
				("post", "/api/method/frappe.core.doctype.user.user.reset_password", {"user": h.AYSE}),
				(
					"post",
					"/api/method/frappe.core.doctype.user.user.sign_up",
					{"email": "x@example.test", "full_name": "X", "redirect_to": "/"},
				),
				("get", "/api/method/frappe.www.login.login_via_token", {"login_token": "x"}),
				(
					"get",
					"/api/method/frappe.integrations.oauth2_logins.login_via_keycloak",
					{"code": "x", "state": "y"},
				),
				(
					"get",
					"/api/method/frappe.integrations.oauth2_logins.login_via_google",
					{"code": "x", "state": "y"},
				),
				(
					"get",
					"/api/method/frappe.integrations.oauth2_logins.custom/keycloak",
					{"code": "x", "state": "y"},
				),
			):
				client = h.new_client()
				if method == "post":
					response = h.request(client.post, path, data=body)
				else:
					response = h.request(client.get, path, query_string=body)
				self.assertEqual(
					response.status_code, 403, f"{path}: {response.status_code} {response.data[:120]}"
				)
			for path in ("/api/v2/method/login", "/api/v1/method/login"):
				# Frappe 16 opens password sessions only for /api/method/login or cmd=login (frappe/auth.py:135);
				# the v1/v2 spellings are no-ops (frappe/api/v2.py:56). Nobody may end up signed in.
				client = h.new_client()
				response = h.request(
					client.post, path, data={"usr": self.admin_user, "pwd": self.admin_password}
				)
				self.assertIn(response.status_code, (200, 401), f"{path}: {response.status_code}")
				self.assertEqual(h.logged_user(client), "Guest", path)
			via_cmd_login = h.request(
				h.new_client().post,
				"/",
				data={"cmd": "login", "usr": self.admin_user, "pwd": self.admin_password},
			)
			self.assertEqual(via_cmd_login.status_code, 401, via_cmd_login.data[:200])

	def test_every_gated_function_answers_403_for_guest_and_signed_in_user(self):
		# Contract `x-yerel-giris-kapisi`: each of the 16 wrappers (LDAP included, minor finding 3) refuses with 403 `PermissionError` while the
		# gate is on, both under Frappe's path (override) and under the wrapper's own path, with or without a session.
		self.assertEqual(len(login_policy.GATED_FUNCTIONS), 16)
		with h.SiteSettings({"identity_keycloak_only": 1}):
			signed_in = h.new_client()
			response = h.login_with_keycloak(signed_in, h.userinfo("sub-ayse", h.AYSE))
			self.assertEqual(response.status_code, 302, response.data[:200])
			for original, (name, methods) in login_policy.GATED_FUNCTIONS.items():
				verb = "post" if methods == ["POST"] else "get"
				for path in (
					f"/api/method/{original}",
					f"/api/method/platform_core.identity.login_policy.{name}",
				):
					for label, client in (("guest", h.new_client()), ("signed in", signed_in)):
						headers = h.csrf_headers(client) if label == "signed in" else {}
						call = getattr(client, verb)
						if verb == "post":
							answer = h.request(call, path, data={"x": "1"}, headers=headers)
						else:
							answer = h.request(call, path, query_string={"x": "1"}, headers=headers)
						self.assertEqual(answer.status_code, 403, f"{label} {path}: {answer.data[:160]}")
						self.assertEqual(answer.json.get("exc_type"), "PermissionError", f"{label} {path}")
			self.assertEqual(h.logged_user(signed_in), h.AYSE)

	def test_gate_off_rejects_missing_local_sign_in_arguments(self):
		with h.SiteSettings({"identity_keycloak_only": 0}):
			website_user = h.new_client()
			response = h.login_with_keycloak(website_user, h.userinfo("sub-ayse", h.AYSE))
			self.assertEqual(response.status_code, 302, response.data[:200])
			for name, methods in login_policy.GATED_FUNCTIONS.values():
				if "GET" not in methods:
					continue
				with self.subTest(name=name):
					path = f"/api/method/platform_core.identity.login_policy.{name}"
					guest = h.request(h.new_client().get, path)
					self.assertEqual(guest.status_code, 400, guest.data[:200])
					self.assertEqual(guest.json.get("exc_type"), "InvalidInput")
					denied = h.request(website_user.get, path)
					self.assertEqual(denied.status_code, 403, denied.data[:200])
					self.assertEqual(denied.json.get("exc_type"), "PermissionError")
			self.assertEqual(h.logged_user(website_user), h.AYSE)

	def test_gate_off_delegates_to_the_original_functions(self):
		# With the gate off the wrappers must behave like Frappe: reset_password answers 200 for any address.
		response = h.request(
			h.new_client().post,
			"/api/method/frappe.core.doctype.user.user.reset_password",
			data={"user": h.AYSE},
		)
		self.assertEqual(response.status_code, 200, response.data[:200])

	def test_portal_block_survives_path_tricks(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
		# `//me` is a scheme-relative URL for browsers and the test client alike, so it is not a path variant.
		for path in ("/me.html", "/./me", "/me/", "/me//", "/update-password/x"):
			response = h.request(client.get, path, follow_redirects=True)
			self.assertEqual(response.status_code, 403, f"{path}: {response.status_code}")

	def test_portal_pages_are_closed_to_end_users(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-ayse", h.AYSE))
		for path in ("/me", "/update-profile", "/update-password", "/third_party_apps", "/portal"):
			response = h.request(client.get, path, follow_redirects=True)
			self.assertEqual(response.status_code, 403, f"{path}: {response.status_code}")

	def test_portal_page_stays_open_to_administrator(self):
		admin = h.new_client()
		admin.set_cookie("sid", self.sid)
		response = h.request(admin.get, "/me", follow_redirects=True)
		self.assertEqual(response.status_code, 200)
