"""G-53: only platform operators open the Desk. Everyone else is sent to the panel.

Expected values come from G-53 in the decision site (`src/data/requirements.json`) and task AJA-801 (D-1).
HTTP requests run through Frappe's test client in a separate thread, like `frappe.tests.test_api`.
Test data is synthetic and committed, because each request opens its own database connection.
"""

import json
from pathlib import Path
from urllib.parse import quote, urlsplit

import frappe
from frappe.auth import CookieManager, LoginManager
from frappe.core.doctype.user.user import generate_keys
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client, set_request

from platform_core import hooks

OPERATOR_ROLE = "Platform Operator"
PANEL_PATH = "/panel"
TENANT_ADMIN_ROLE = "Desk Policy Tenant Admin"
TENANT_ADMIN = "desk-policy-admin@example.test"
OPERATOR = "desk-policy-operator@example.test"
PORTAL_USER = "desk-policy-portal@example.test"
SETTINGS_HOOK = "platform_core.config.desk_policy.apply"
REQUEST_HOOK = "platform_core.config.desk_policy.before_request"
AUTH_HOOK = "platform_core.config.desk_policy.after_auth"
OAUTH_CLIENT = "desk-policy-oauth-client"
# Frappe resolves these to the Desk (`frappe/website/path_resolver.py`). AJA-846 found them.
DESK_PATH_SPELLINGS = ("/desk/..", "/desk/x/../..", "/desk%20", "/desk.html")


def _user(email, roles, user_type="System User"):
	if frappe.db.exists("User", email):
		doc = frappe.get_doc("User", email)
	else:
		doc = frappe.new_doc("User")
		doc.update({"email": email, "first_name": "Sample", "send_welcome_email": 0})
	doc.user_type = user_type
	doc.set("roles", [{"role": role} for role in roles])
	doc.save(ignore_permissions=True)


def _sid(user):
	set_request(path="/")
	frappe.local.cookie_manager = CookieManager()
	frappe.local.login_manager = LoginManager()
	frappe.local.login_manager.login_as(user)
	sid = frappe.session.sid
	frappe.set_user("Administrator")
	return sid


def _bearer_token(user):
	client_id = frappe.db.get_value("OAuth Client", {"app_name": OAUTH_CLIENT}, "client_id")
	if not client_id:
		client = frappe.get_doc(
			{
				"doctype": "OAuth Client",
				"app_name": OAUTH_CLIENT,
				"grant_type": "Authorization Code",
				"redirect_uris": "http://localhost",
				"default_redirect_uri": "http://localhost",
				"response_type": "Code",
				"scopes": "all",
				"skip_authorization": 1,
			}
		).insert(ignore_permissions=True)
		client_id = client.client_id
	access_token = frappe.generate_hash()
	frappe.get_doc(
		{
			"doctype": "OAuth Bearer Token",
			"access_token": access_token,
			"client": client_id,
			"expires_in": 3600,
			"scopes": "all",
			"status": "Active",
			"user": user,
		}
	).insert(ignore_permissions=True)
	return access_token


class TestDeskPolicy(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", TENANT_ADMIN_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": TENANT_ADMIN_ROLE, "desk_access": 1}).insert()
		_user(TENANT_ADMIN, [TENANT_ADMIN_ROLE])
		_user(OPERATOR, [TENANT_ADMIN_ROLE, OPERATOR_ROLE])
		_user(PORTAL_USER, [], user_type="Website User")
		frappe.db.commit()
		cls.sids = {user: _sid(user) for user in (TENANT_ADMIN, OPERATOR, PORTAL_USER)}
		cls.api_keys = {user: generate_keys(user) for user in (TENANT_ADMIN, OPERATOR)}
		cls.bearer_tokens = {user: _bearer_token(user) for user in (TENANT_ADMIN, OPERATOR)}
		frappe.db.commit()

	def get(self, path, user=None, *, follow_redirects=False, headers=None):
		client = get_test_client()
		if user:
			client.set_cookie("sid", self.sids[user])
		kwargs = {"follow_redirects": follow_redirects, "headers": headers or {}}
		return make_request(target=client.get, args=(path,), kwargs=kwargs)

	def api_key_header(self, user):
		keys = self.api_keys[user]
		return {"Authorization": f"token {keys['api_key']}:{keys['api_secret']}"}

	def bearer_header(self, user):
		return {"Authorization": f"Bearer {self.bearer_tokens[user]}"}

	def assert_sent_to_panel(self, path, user=TENANT_ADMIN, *, headers=None):
		response = self.get(path, user if headers is None else None, headers=headers)
		self.assertEqual(response.status_code, 302, f"{path}: {response.status_code}")
		self.assertEqual(urlsplit(response.headers["Location"]).path, PANEL_PATH, path)

	# --- The role -----------------------------------------------------------------------------------

	def test_platform_operator_role_exists_with_desk_access(self):
		self.assertEqual(frappe.db.get_value("Role", OPERATOR_ROLE, "desk_access"), 1)

	def test_role_is_shipped_as_a_fixture_for_new_tenants(self):
		fixture = Path(frappe.get_app_path("platform_core", "fixtures", "role.json"))
		roles = {row["name"]: row for row in json.loads(fixture.read_text())}
		self.assertEqual(roles[OPERATOR_ROLE]["desk_access"], 1)
		names = set()
		for entry in hooks.fixtures:
			if entry["dt"] == "Role":
				for _field, operator, value in entry["filters"]:
					names.update(value if operator == "in" else [value])
		self.assertIn(OPERATOR_ROLE, names)

	# --- The request hook ---------------------------------------------------------------------------

	def test_request_hook_runs_after_the_session_policy(self):
		self.assertIn(REQUEST_HOOK, hooks.before_request)
		self.assertGreater(
			hooks.before_request.index(REQUEST_HOOK),
			hooks.before_request.index("platform_core.identity.session_policy.before_request"),
		)

	def test_tenant_admin_is_sent_from_app_to_the_panel(self):
		self.assert_sent_to_panel("/app")

	def test_tenant_admin_is_sent_from_desk_to_the_panel(self):
		self.assert_sent_to_panel("/desk")

	def test_tenant_admin_is_sent_from_any_desk_page_to_the_panel(self):
		for path in ("/app/", "/app/user", "/app/user/new", "/desk/", "/desk/user", "/app//user"):
			with self.subTest(path=path):
				self.assert_sent_to_panel(path)

	def test_desk_path_spellings_that_frappe_resolves_are_redirected(self):
		for path in DESK_PATH_SPELLINGS:
			with self.subTest(path=path):
				self.assert_sent_to_panel(path)

	def test_desk_path_check_follows_frappe_path_rules(self):
		from platform_core.config.desk_policy import is_desk_path

		for path in ("/desk", "/desk/..", "/desk/x/../..", "/desk ", " /desk/ ", "/desk.html", "/app.html"):
			with self.subTest(path=path):
				self.assertTrue(is_desk_path(path))
		for path in ("/", "/desktop", "/apple", "/panel", "/api/method/x", "/x/../desk", "/desk.htm"):
			with self.subTest(path=path):
				self.assertFalse(is_desk_path(path))

	def test_auth_hook_runs_after_the_credential_hooks(self):
		self.assertIn(AUTH_HOOK, hooks.auth_hooks)
		self.assertEqual(hooks.auth_hooks[-1], AUTH_HOOK)

	def test_api_key_request_to_the_desk_is_redirected(self):
		for path in ("/desk", "/app/user", "/desk.html"):
			with self.subTest(path=path):
				self.assert_sent_to_panel(path, headers=self.api_key_header(TENANT_ADMIN))

	def test_oauth_token_request_to_the_desk_is_redirected(self):
		for path in ("/desk", "/desk/user"):
			with self.subTest(path=path):
				self.assert_sent_to_panel(path, headers=self.bearer_header(TENANT_ADMIN))

	def test_platform_operator_opens_the_desk_with_an_api_key(self):
		response = self.get("/desk", headers=self.api_key_header(OPERATOR))
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"frappe.boot =", response.data)

	def test_api_paths_keep_working_with_an_api_key(self):
		for headers in (self.api_key_header(TENANT_ADMIN), self.bearer_header(TENANT_ADMIN)):
			response = self.get("/api/method/frappe.auth.get_logged_user", headers=headers)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.json["message"], TENANT_ADMIN)

	def test_tenant_admin_never_sees_403_on_desk_addresses(self):
		for path in ("/app", "/desk", "/app/user"):
			with self.subTest(path=path):
				response = self.get(path, TENANT_ADMIN, follow_redirects=True)
				self.assertNotEqual(response.status_code, 403, path)
				self.assertEqual(response.request.path, PANEL_PATH, path)

	def test_website_user_is_also_sent_to_the_panel(self):
		for path in ("/app", "/desk", "/app/user"):
			with self.subTest(path=path):
				self.assert_sent_to_panel(path, PORTAL_USER)

	def test_platform_operator_opens_the_desk(self):
		response = self.get("/desk", OPERATOR)
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"frappe.boot =", response.data)
		response = self.get("/app/user", OPERATOR, follow_redirects=True)
		self.assertEqual(response.status_code, 200)
		self.assertNotEqual(response.request.path, PANEL_PATH)

	def test_administrator_keeps_the_desk(self):
		client = get_test_client()
		client.set_cookie("sid", _sid("Administrator"))
		frappe.db.commit()
		response = make_request(target=client.get, args=("/desk",))
		self.assertEqual(response.status_code, 200)

	def test_guest_is_not_sent_to_the_panel(self):
		# Frappe asks a guest to sign in first. The sign-in page then decides where to go.
		response = self.get("/desk")
		if response.status_code in (301, 302, 303, 307, 308):
			self.assertNotEqual(urlsplit(response.headers["Location"]).path, PANEL_PATH)

	def test_similar_paths_are_not_redirected(self):
		for path in ("/apple", "/desktop", "/panel", "/api/method/frappe.auth.get_logged_user"):
			with self.subTest(path=path):
				response = self.get(path, TENANT_ADMIN)
				location = response.headers.get("Location") or ""
				self.assertFalse(
					response.status_code == 302
					and urlsplit(location).path == PANEL_PATH
					and path != PANEL_PATH,
					f"{path}: {response.status_code} {location}",
				)

	# --- Settings -----------------------------------------------------------------------------------

	def test_settings_hook_runs_on_install_and_on_migrate(self):
		self.assertIn(SETTINGS_HOOK, hooks.after_install)
		self.assertIn(SETTINGS_HOOK, hooks.after_migrate)

	def test_settings_have_the_g53_values(self):
		self.assertEqual(
			frappe.db.get_single_value("System Settings", "disable_system_update_notification"), 1
		)
		self.assertEqual(frappe.db.get_single_value("System Settings", "disable_change_log_notification"), 1)
		self.assertEqual(frappe.db.get_single_value("System Settings", "enable_onboarding"), 0)
		self.assertEqual(frappe.db.get_single_value("Website Settings", "home_page"), PANEL_PATH.lstrip("/"))

	def test_new_tenant_gets_the_settings(self):
		from platform_core.config import desk_policy

		frappe.db.set_single_value(
			"System Settings",
			{
				"disable_system_update_notification": 0,
				"disable_change_log_notification": 0,
				"enable_onboarding": 1,
			},
		)
		frappe.db.set_single_value("Website Settings", "home_page", "")
		desk_policy.apply()
		self.test_settings_have_the_g53_values()

	# --- Protected settings stay closed -------------------------------------------------------------

	def test_tenant_admin_cannot_read_protected_settings(self):
		for doctype, name in (
			("System Settings", "System Settings"),
			("Social Login Key", None),
			("Email Account", None),
		):
			path = "/api/resource/" + quote(doctype) + (("/" + quote(name)) if name else "")
			with self.subTest(doctype=doctype):
				self.assertEqual(self.get(path, TENANT_ADMIN).status_code, 403)
