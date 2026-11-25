"""G-98: the “Tenant Admin” invites users and gives them role profiles (AJA-791).

The expected results come from G-16, G-62, G-79 and G-98 of the decision site and from the
identity-sync contract (`contracts/identity_sync.openapi.yaml`, `/v1/invitations`) (D-1).

A tenant is its own Frappe site. A user of the tenant is a Website User linked to the site's
Keycloak issuer (`PLT Identity Link`). A user without such a link belongs to no tenant of this
site, for example a user of another tenant. Such a request gets 403, as a missing user does.

identity-sync is replaced by a fake transport. No request leaves the test. All people are made up.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password

from platform_core.identity import user_admin
from platform_core.identity.tests import helpers as h

API = "/api/method/platform_core.api.identity."
SIGN_IN_PHRASE = "Sahte-Parola-7910-tu!"
# The access module makes the role on install and migrate (`tenant_admin.ensure_role`).
TENANT_ADMIN = "Tenant Admin"
HOLDER = "tu.yonetici@example.test"
MEMBER = "tu.uye@example.test"
# A Website User on the site without a link to the tenant's issuer.
STRANGER = "tu.yabanci@example.test"
SYSTEM_MANAGER_USER = "tu.sistem@example.test"
PLAIN_ROLE = "TU Deneme Rol"
PROFILE = "TU Deneme Profil"
PROTECTED_PROFILE = "TU Korunan Profil"
ORGANIZATION = "org-tenant1-fake"
SERVICE_URL = "https://identity-sync.internal.example.test"
BEARER = "fake-service-bearer"
DIGEST = "a" * 64
INVITEE = "tu.davetli@example.test"
PREVIEWS = [{"operation": "create_user", "target": "user", "destructive": False}]
INVITE_COUNTER = "rl:platform_core.api.identity.invite_user:"


class FakeIdentitySync:
	"""Answers `_send` like identity-sync. Records each request."""

	def __init__(self, status: int = 200, body: object = None):
		self.status = status
		self.body = body
		self.calls: list[tuple[str, str, dict | None]] = []

	def __call__(self, method: str, url: str, payload: object, bearer: str):
		self.calls.append((method, url, payload))
		if self.body is not None or self.status != 200:
			return self.status, self.body
		if payload.get("dry_run"):
			return 200, {"subject": None, "previews": PREVIEWS, "preview_digest": DIGEST, "extra": "x"}
		return 200, {"subject": "kc-sub-1", "previews": PREVIEWS}


def _user(email: str, roles: list[str], user_type: str = "Website User") -> None:
	if frappe.db.exists("User", email):
		doc = frappe.get_doc("User", email)
		doc.set("role_profiles", [])
		doc.set("roles", [{"role": role} for role in roles])
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			doctype="User",
			email=email,
			first_name=email.split("@")[0],
			send_welcome_email=0,
			user_type=user_type,
			roles=[{"role": role} for role in roles],
		).insert(ignore_permissions=True)
	update_password(email, SIGN_IN_PHRASE)


def _link(email: str) -> None:
	if not frappe.db.exists("PLT Identity Link", {"issuer": h.ISSUER, "user": email}):
		frappe.get_doc(
			doctype="PLT Identity Link", issuer=h.ISSUER, subject="sub-" + email, user=email
		).insert(ignore_permissions=True)


def _profile(name: str, roles: list[str]) -> None:
	if not frappe.db.exists("Role Profile", name):
		frappe.get_doc(
			doctype="Role Profile", role_profile=name, roles=[{"role": role} for role in roles]
		).insert(ignore_permissions=True)


class TenantUsersCase(IntegrationTestCase):
	"""The people, profiles and request helpers of the G-98 tests. It has no tests of its own.

	`api/test_identity.py` uses it for the endpoint tests that the security gate names.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site = frappe.local.site
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", TENANT_ADMIN):
			raise AssertionError("The Tenant Admin role is made on install.")
		if not frappe.db.exists("Role", PLAIN_ROLE):
			frappe.get_doc(doctype="Role", role_name=PLAIN_ROLE, desk_access=0).insert()
		_profile(PROFILE, [PLAIN_ROLE])
		_profile(PROTECTED_PROFILE, ["System Manager"])
		_user(HOLDER, [TENANT_ADMIN])
		_user(MEMBER, [])
		_user(STRANGER, [])
		_user(SYSTEM_MANAGER_USER, ["System Manager"], user_type="System User")
		for email in (HOLDER, MEMBER, SYSTEM_MANAGER_USER):
			_link(email)
		frappe.db.commit()  # nosemgrep: frappe-test-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		users = (HOLDER, MEMBER, STRANGER, SYSTEM_MANAGER_USER)
		frappe.db.delete("PLT Identity Link", {"user": ("in", users)})
		frappe.db.delete("User Role Profile", {"role_profile": ("in", [PROFILE, PROTECTED_PROFILE])})
		for name in (PROFILE, PROTECTED_PROFILE):
			frappe.delete_doc("Role Profile", name, ignore_permissions=True, force=True)
		frappe.db.commit()  # nosemgrep: frappe-test-commit
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		settings = h.SiteSettings(
			{"mobile_identity_sync_url": SERVICE_URL, "keycloak_organization_id": ORGANIZATION}
		)
		settings.__enter__()
		self.addCleanup(settings.__exit__, None, None, None)
		bearer = patch.object(user_admin, "identity_sync_bearer", return_value=BEARER)
		bearer.start()
		self.addCleanup(bearer.stop)
		# `invite_user` counts requests per user. Each test starts with fresh counters.
		frappe.cache.delete_keys(INVITE_COUNTER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		_user(MEMBER, [])
		_user(SYSTEM_MANAGER_USER, ["System Manager"], user_type="System User")
		frappe.db.commit()  # nosemgrep: frappe-test-commit
		super().tearDown()

	# --- request helpers ---

	def send(self, client, path: str, body=None, method: str = "POST", query=None):
		headers = {"Accept": "application/json"}
		kwargs = {"path": path, "method": method, "headers": headers}
		if body is not None:
			headers["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		if query:
			kwargs["query_string"] = query
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def login(self, user: str = HOLDER):
		client = get_test_client(use_cookies=True)
		response = self.send(client, "/api/method/login", {"usr": user, "pwd": SIGN_IN_PHRASE})
		self.assertEqual(response.status_code, 200)
		return client

	def serve(self, fake: FakeIdentitySync) -> FakeIdentitySync:
		transport = patch.object(user_admin, "_send", fake)
		transport.start()
		self.addCleanup(transport.stop)
		return fake

	def assign(self, client, user: str, profiles: list[str]):
		return self.send(client, API + "set_user_role_profiles", {"user": user, "role_profiles": profiles})

	def invite(self, client, **body):
		return self.send(client, API + "invite_user", {"email": INVITEE, **body})


class TestTenantUsers(TenantUsersCase):
	# --- role profile ---

	def test_holder_gives_a_role_profile_to_a_tenant_user(self):
		client = self.login()
		response = self.assign(client, MEMBER, [PROFILE])
		self.assertEqual(response.status_code, 200, response.data[:500])
		message = response.json["message"]
		self.assertEqual(message["user"], MEMBER)
		self.assertEqual(message["role_profiles"], [PROFILE])
		self.assertIn(PLAIN_ROLE, message["roles"])
		self.assertIn(PLAIN_ROLE, frappe.get_roles(MEMBER))
		# The user stays a Website User.
		self.assertEqual(frappe.db.get_value("User", MEMBER, "user_type"), "Website User")

	def test_profile_with_a_protected_role_is_refused(self):
		client = self.login()
		response = self.assign(client, MEMBER, [PROTECTED_PROFILE])
		self.assertEqual(response.status_code, 403, response.data[:500])
		self.assertNotIn("System Manager", frappe.get_roles(MEMBER))

	def test_user_of_another_tenant_gets_403(self):
		client = self.login()
		# The user exists on the site but has no link to this tenant's issuer.
		response = self.assign(client, STRANGER, [PROFILE])
		self.assertEqual(response.status_code, 403, response.data[:500])
		self.assertNotIn(PLAIN_ROLE, frappe.get_roles(STRANGER))

	def test_missing_user_gets_the_same_403(self):
		client = self.login()
		response = self.assign(client, "tu.yok@example.test", [PROFILE])
		self.assertEqual(response.status_code, 403, response.data[:500])

	def test_system_manager_and_administrator_are_not_touched(self):
		client = self.login()
		for user in (SYSTEM_MANAGER_USER, "Administrator"):
			response = self.assign(client, user, [PROFILE])
			self.assertEqual(response.status_code, 403, (user, response.data[:500]))
		self.assertIn("System Manager", frappe.get_roles(SYSTEM_MANAGER_USER))

	def test_unknown_profile_gets_404(self):
		client = self.login()
		response = self.assign(client, MEMBER, ["TU Olmayan Profil"])
		self.assertEqual(response.status_code, 404, response.data[:500])

	def test_profile_list_must_be_a_list_of_names(self):
		client = self.login()
		response = self.send(client, API + "set_user_role_profiles", {"user": MEMBER, "role_profiles": 5})
		self.assertEqual(response.status_code, 400, response.data[:500])

	def test_plain_user_cannot_give_role_profiles(self):
		client = self.login(MEMBER)
		response = self.assign(client, MEMBER, [PROFILE])
		self.assertEqual(response.status_code, 403, response.data[:500])
		self.assertNotIn(PLAIN_ROLE, frappe.get_roles(MEMBER))

	def test_get_is_refused_for_the_change(self):
		client = self.login()
		response = self.send(
			client,
			API + "set_user_role_profiles",
			method="GET",
			query={"user": MEMBER, "role_profiles": "[]"},
		)
		self.assertNotEqual(response.status_code, 200)

	# --- invitation ---

	def test_holder_previews_an_invitation(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		response = self.invite(client, first_name="Deniz", dry_run=True)
		self.assertEqual(response.status_code, 200, response.data[:500])
		self.assertEqual(
			response.json["message"],
			{"dry_run": True, "subject": None, "previews": PREVIEWS, "preview_digest": DIGEST},
		)
		method, url, payload = fake.calls[0]
		self.assertEqual((method, url), ("POST", SERVICE_URL + "/v1/invitations"))
		# The organization comes from the site config, never from the request.
		self.assertEqual(
			payload,
			{"email": INVITEE, "first_name": "Deniz", "organization_id": ORGANIZATION, "dry_run": True},
		)

	def test_holder_runs_the_previewed_invitation(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		response = self.invite(client, first_name="Deniz", dry_run=False, preview_digest=DIGEST)
		self.assertEqual(response.status_code, 200, response.data[:500])
		self.assertEqual(
			response.json["message"], {"dry_run": False, "subject": "kc-sub-1", "previews": PREVIEWS}
		)
		payload = fake.calls[0][2]
		self.assertIs(payload["dry_run"], False)
		self.assertEqual(payload["preview_digest"], DIGEST)
		self.assertRegex(payload["approval_id"], r"^[A-Za-z0-9_-]{1,128}$")
		# Each run carries a new approval id.
		self.invite(client, first_name="Deniz", dry_run=False, preview_digest=DIGEST)
		self.assertNotEqual(fake.calls[1][2]["approval_id"], payload["approval_id"])

	def test_organization_field_in_the_body_is_refused(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		response = self.invite(client, dry_run=True, organization_id="org-other")
		self.assertEqual(response.status_code, 400, response.data[:500])
		self.assertEqual(fake.calls, [])

	def test_run_without_a_digest_is_refused(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		for body in ({"dry_run": False}, {"dry_run": False, "preview_digest": "xyz"}, {}):
			response = self.invite(client, **body)
			self.assertEqual(response.status_code, 400, (body, response.data[:500]))
		self.assertEqual(fake.calls, [])

	def test_invalid_email_is_refused(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		response = self.send(client, API + "invite_user", {"email": "not-an-email", "dry_run": True})
		self.assertEqual(response.status_code, 400, response.data[:500])
		self.assertEqual(fake.calls, [])

	def test_desk_user_email_is_not_invited(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		response = self.send(client, API + "invite_user", {"email": SYSTEM_MANAGER_USER, "dry_run": True})
		self.assertEqual(response.status_code, 409, response.data[:500])
		self.assertEqual(fake.calls, [])

	def test_changed_preview_gives_409(self):
		self.serve(FakeIdentitySync(status=409))
		client = self.login()
		response = self.invite(client, dry_run=False, preview_digest=DIGEST)
		self.assertEqual(response.status_code, 409, response.data[:500])

	def test_refused_organization_gives_403(self):
		self.serve(FakeIdentitySync(status=403))
		client = self.login()
		response = self.invite(client, dry_run=True)
		self.assertEqual(response.status_code, 403, response.data[:500])

	def test_service_outage_gives_503(self):
		self.serve(FakeIdentitySync(status=502))
		client = self.login()
		response = self.invite(client, dry_run=True)
		self.assertEqual(response.status_code, 503, response.data[:500])
		self.assertNotIn(BEARER, response.get_data(as_text=True))

	def test_site_without_organization_makes_no_call(self):
		fake = self.serve(FakeIdentitySync())
		# `update_site_config` removes a key only for the literal "None".
		with h.SiteSettings({"keycloak_organization_id": "None"}):
			frappe.local.conf.pop("keycloak_organization_id", None)
			client = self.login()
			response = self.invite(client, dry_run=True)
		self.assertEqual(response.status_code, 503, response.data[:500])
		self.assertEqual(fake.calls, [])

	def test_plain_user_cannot_invite(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login(MEMBER)
		response = self.invite(client, dry_run=True)
		self.assertEqual(response.status_code, 403, response.data[:500])
		self.assertEqual(fake.calls, [])

	def test_many_invitations_in_a_short_time_are_stopped_per_user(self):
		"""Each user may send `INVITE_LIMIT` invitation requests in `INVITE_WINDOW` seconds (AJA-890)."""
		from platform_core.api import identity

		self.assertGreater(identity.INVITE_LIMIT, 0)
		self.assertGreater(identity.INVITE_WINDOW, 0)
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		for _attempt in range(identity.INVITE_LIMIT):
			self.assertEqual(self.invite(client, dry_run=True).status_code, 200)
		calls = len(fake.calls)
		response = self.invite(client, dry_run=True)
		self.assertEqual(response.status_code, 429, response.data[:500])
		self.assertNotIn("message", response.json)
		# The stopped request does not reach identity-sync.
		self.assertEqual(len(fake.calls), calls)
		# The counter belongs to the user. Another manager of the tenant can still invite.
		other = self.login(SYSTEM_MANAGER_USER)
		self.assertEqual(self.invite(other, dry_run=True).status_code, 200)
