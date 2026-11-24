"""AtonotA Login reads through Frappe's HTTP dispatch (AJA-459).

Expected values come from the security review (AJA-458) and from the panel contract
(`atonota-web`, `src/auth/README.md`, sections G-159 and G-160) (D-1):

- `list_login_providers` returns `{"providers": [{"alias", "display_name"}]}`.
- `list_linked_accounts` returns `{"providers": [{"alias", "display_name", "linked"}], "local_sign_in_methods": <count>}`.

The identity-sync service is replaced at the transport function. Its replies follow
`contracts/identity_sync.openapi.yaml`. The real service runs in the backend trial (D-6).
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import login_accounts, provider_setup
from platform_core.identity.tests import helpers as h

PREFIX = "/api/method/platform_core.api.auth."
PROVIDERS = PREFIX + "list_login_providers"
LINKED = PREFIX + "list_linked_accounts"
SERVICE_URL = "https://identity-sync.internal.example.test"
BEARER = "fixture-bearer-value"
SUBJECT = "fixture-first"
OTHER_SUBJECT = "fixture-second"

PROVIDER_REPLY = {"providers": [{"alias": "google", "display_name": "Google"}]}
LINKED_REPLY = {
	"providers": [
		{"alias": "google", "display_name": "Google", "linked": True},
		{"alias": "tenant1-sso", "display_name": "Tenant One SSO", "linked": False},
	],
	"local_sign_in_methods": 1,
}
# Fields an upstream reply must never pass through, even when the service sent them.
LEAKY_REPLY = {
	"providers": [
		{
			"alias": "google",
			"display_name": "Google",
			"linked": True,
			"config": {"clientSecret": "fixture-secret-value"},
			"userName": "ayse.ornek@elsewhere.example.test",
		}
	],
	"local_sign_in_methods": 1,
	"credentials": [{"id": "credential-id", "credentialData": "fixture-hash-value"}],
}


def clear_sample_links():
	frappe.db.delete("PLT Identity Link", {"user": ["in", [h.AYSE, h.MEHMET]]})
	h.refresh()


class FakeIdentitySync:
	"""Stands in for the transport. Records each call and answers like the service."""

	def __init__(self, replies: dict[str, tuple[int, object]] | None = None, error: Exception | None = None):
		self.replies = replies or {
			"/v1/login-providers": (200, PROVIDER_REPLY),
			"/v1/linked-accounts": (200, LINKED_REPLY),
		}
		self.error = error
		self.calls: list[tuple[str, str, object, str]] = []

	def __call__(self, method: str, url: str, payload: object, bearer: str) -> tuple[int, object]:
		self.calls.append((method, url, payload, bearer))
		if self.error is not None:
			raise self.error
		path = url.removeprefix(SERVICE_URL)
		return self.replies[path]


class TestLoginReads(FrappeAPITestCase):
	def setUp(self):
		super().setUp()
		settings = h.SiteSettings({"mobile_identity_sync_url": SERVICE_URL})
		settings.__enter__()
		self.addCleanup(settings.__exit__, None, None, None)
		clear_sample_links()
		h.clear_links()
		self.addCleanup(h.clear_links)
		# A test moves a link to another issuer. `h.clear_links` keeps such rows, so remove them by user.
		self.addCleanup(clear_sample_links)
		provider_setup.ensure_social_login_key()
		for user in (h.AYSE, h.MEHMET):
			h.ensure_user(user)
		h.refresh()
		h.reset_rate_limits()
		bearer = patch.object(login_accounts, "identity_sync_bearer", return_value=BEARER)
		bearer.start()
		self.addCleanup(bearer.stop)

	def login(self, user=h.AYSE, subject=SUBJECT):
		client = h.new_client()
		with h.jwks_patch():
			self.assertEqual(h.login_with_keycloak(client, h.userinfo(subject, user)).status_code, 302)
		self.assertEqual(h.logged_user(client), user)
		return client

	def serve(self, fake: FakeIdentitySync):
		transport = patch.object(login_accounts, "_send", fake)
		transport.start()
		self.addCleanup(transport.stop)
		return fake

	# --- the signed-in user gets the panel's reply shape ---

	def test_signed_in_user_reads_the_platform_list(self):
		fake = self.serve(FakeIdentitySync())
		response = h.request(self.login().get, PROVIDERS)
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], PROVIDER_REPLY)
		# The platform list takes no person: no body, no subject.
		self.assertEqual(fake.calls, [("GET", SERVICE_URL + "/v1/login-providers", None, BEARER)])

	def test_signed_in_user_reads_the_own_linked_accounts(self):
		fake = self.serve(FakeIdentitySync())
		response = h.request(self.login().get, LINKED)
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], LINKED_REPLY)
		# The subject comes from the session and its identity link, never from the request.
		self.assertEqual(
			fake.calls, [("POST", SERVICE_URL + "/v1/linked-accounts", {"subject": SUBJECT}, BEARER)]
		)

	def test_reply_fields_match_the_panel_contract(self):
		self.serve(FakeIdentitySync())
		client = self.login()
		providers = h.request(client.get, PROVIDERS).json["message"]
		linked = h.request(client.get, LINKED).json["message"]
		self.assertEqual(set(providers), {"providers"})
		self.assertEqual(set(providers["providers"][0]), {"alias", "display_name"})
		self.assertEqual(set(linked), {"providers", "local_sign_in_methods"})
		self.assertEqual(set(linked["providers"][0]), {"alias", "display_name", "linked"})
		self.assertIsInstance(linked["local_sign_in_methods"], int)

	def test_upstream_fields_outside_the_allow_list_are_dropped(self):
		self.serve(
			FakeIdentitySync(
				{
					"/v1/login-providers": (200, {"providers": [{**LEAKY_REPLY["providers"][0]}]}),
					"/v1/linked-accounts": (200, LEAKY_REPLY),
				}
			)
		)
		client = self.login()
		for path in (PROVIDERS, LINKED):
			with self.subTest(path=path):
				response = h.request(client.get, path)
				self.assertEqual(response.status_code, 200, response.data[:300])
				text = json.dumps(response.json)
				for leak in (
					"config",
					"clientSecret",
					"fixture-secret-value",
					"userName",
					"elsewhere",
					"credentialData",
					"fixture-hash-value",
				):
					self.assertNotIn(leak, text)

	def test_replies_are_not_stored(self):
		self.serve(FakeIdentitySync())
		client = self.login()
		for path in (PROVIDERS, LINKED):
			with self.subTest(path=path):
				response = h.request(client.get, path)
				directives = {part.strip() for part in response.headers.get("Cache-Control", "").split(",")}
				self.assertIn("no-store", directives)

	# --- refusals ---

	def test_guest_gets_403_not_417(self):
		fake = self.serve(FakeIdentitySync())
		for path in (PROVIDERS, LINKED):
			with self.subTest(path=path):
				response = h.request(h.new_client().get, path)
				self.assertEqual(response.status_code, 403)
				self.assertEqual(response.json["exc_type"], "PermissionError")
		self.assertEqual(fake.calls, [])

	def test_subject_or_user_parameter_is_refused(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		for path in (PROVIDERS, LINKED):
			for name in ("subject", "user"):
				with self.subTest(path=path, name=name):
					response = h.request(client.get, path, query_string={name: OTHER_SUBJECT})
					self.assertEqual(response.status_code, 400)
					self.assertEqual(response.json["exc_type"], "InvalidInput")
		self.assertEqual(fake.calls, [])

	def test_session_without_a_matching_identity_link_makes_no_call(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		# The link now names another person. The session subject no longer matches it.
		frappe.db.set_value("PLT Identity Link", {"user": h.AYSE}, "subject", OTHER_SUBJECT)
		h.refresh()
		response = h.request(client.get, LINKED)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "IdentityLinkMissing")
		self.assertEqual(fake.calls, [])

	def test_identity_link_of_another_issuer_makes_no_call(self):
		fake = self.serve(FakeIdentitySync())
		client = self.login()
		frappe.db.set_value(
			"PLT Identity Link", {"user": h.AYSE}, "issuer", "https://other.example.test/realms/platform"
		)
		h.refresh()
		response = h.request(client.get, LINKED)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(fake.calls, [])

	def test_member_of_another_tenant_gets_403(self):
		# identity-sync answers 403 when the person is not a member of the calling tenant.
		self.serve(FakeIdentitySync({"/v1/linked-accounts": (403, {"error": "forbidden"})}))
		response = h.request(self.login().get, LINKED)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "LoginReadForbidden")

	def test_refused_site_client_gets_403(self):
		# Operator, preview and deletion clients get 403 from identity-sync. The method passes it on.
		self.serve(FakeIdentitySync({"/v1/login-providers": (403, {"error": "forbidden"})}))
		response = h.request(self.login().get, PROVIDERS)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json["exc_type"], "LoginReadForbidden")

	def test_service_outage_gives_a_plain_error_without_secrets(self):
		outages = (
			FakeIdentitySync(error=OSError(f"connection refused: {SERVICE_URL} Bearer {BEARER}")),
			FakeIdentitySync(
				{
					"/v1/login-providers": (502, {"error": "upstream_failed"}),
					"/v1/linked-accounts": (502, {"error": "upstream_failed"}),
				}
			),
			FakeIdentitySync(
				{"/v1/login-providers": (200, {"providers": "broken"}), "/v1/linked-accounts": (200, None)}
			),
		)
		client = self.login()
		for fake in outages:
			transport = patch.object(login_accounts, "_send", fake)
			with transport:
				for path in (PROVIDERS, LINKED):
					with self.subTest(path=path, fake=fake.replies if fake.error is None else "error"):
						response = h.request(client.get, path)
						self.assertEqual(response.status_code, 503, response.data[:300])
						self.assertEqual(response.json["exc_type"], "IdentityServiceUnavailable")
						text = response.data.decode("utf-8")
						for secret in (
							BEARER,
							SERVICE_URL,
							"identity-sync.internal",
							"test-client-secret-fake",
							"Traceback",
						):
							self.assertNotIn(secret, text)

	def test_outage_writes_no_error_log_row(self):
		self.serve(FakeIdentitySync(error=OSError("connection refused")))
		client = self.login()
		before = frappe.db.count("Error Log")
		for path in (PROVIDERS, LINKED):
			self.assertEqual(h.request(client.get, path).status_code, 503)
		h.refresh()
		self.assertEqual(frappe.db.count("Error Log"), before)

	def test_rejected_bearer_is_dropped_and_retried_once(self):
		fake = self.serve(FakeIdentitySync({"/v1/login-providers": (401, {"error": "unauthorized"})}))
		with patch.object(login_accounts, "invalidate_identity_sync_bearer") as invalidate:
			response = h.request(self.login().get, PROVIDERS)
		self.assertEqual(response.status_code, 503)
		invalidate.assert_called_with(BEARER)
		self.assertEqual(len(fake.calls), 2)

	def test_post_is_refused(self):
		self.serve(FakeIdentitySync())
		client = self.login()
		for path in (PROVIDERS, LINKED):
			with self.subTest(path=path):
				response = h.request(client.post, path, headers=h.csrf_headers(client))
				self.assertEqual(response.status_code, 403)

	def test_methods_are_rate_limited(self):
		self.serve(FakeIdentitySync())
		client = self.login()
		statuses = [
			h.request(client.get, LINKED).status_code for _attempt in range(login_accounts.RATE_LIMIT + 1)
		]
		self.assertEqual(statuses[:-1], [200] * login_accounts.RATE_LIMIT)
		self.assertEqual(statuses[-1], 429)
