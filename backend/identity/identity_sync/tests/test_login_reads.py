"""The two read endpoints of AtonotA Login (AJA-459): sign-in platforms and linked accounts.

Requests use the real HTTP path (D-6). The expected replies come from the security review
(AJA-458) and from the panel contract (`atonota-web`, `src/auth/README.md`):

- `GET /v1/login-providers` returns `{"providers": [{"alias", "display_name"}]}`.
- `POST /v1/linked-accounts` takes `{"subject"}` and returns
  `{"providers": [{"alias", "display_name", "linked"}], "local_sign_in_methods": <count>}`.

Only tenant site clients may call. The tenant comes from the token's `azp`, never from the body.
"""

from __future__ import annotations

import json
import unittest

from identity_sync import login_reads
from identity_sync.httpjson import TransportError

from .fakes import ORG_ID, SUBJECT, keycloak_user
from .test_server import (
    EXECUTE_TOKEN,
    OPERATOR_TOKEN,
    OTHER_SITE_TOKEN,
    PRESS_TOKEN,
    PREVIEW_TOKEN,
    SESSION_TOKEN,
    ServerCase,
    fake_verifier,
)

PROVIDERS = "/v1/login-providers"
LINKED = "/v1/linked-accounts"
OTHER_USER = "99999999-9999-4999-8999-999999999999"
OTHER_ORG_ID = "33333333-3333-4333-8333-333333333333"
# Values that must never leave the service. The fake Keycloak returns all of them.
LEAKS = ("clientSecret", "**********", "config", "credentialData", "userName", "outside-", "credential-", "idp-")


class LoginReadCase(ServerCase):
    two_tenants = True

    def setUp(self) -> None:
        super().setUp()
        kc = self.stack.keycloak
        other_org = kc.add_organization(OTHER_ORG_ID, "tenant2")
        kc.add_user(keycloak_user(subject=OTHER_USER, email="ikinci@example.test"), [other_org])
        # General platforms: one usable, one hidden, one disabled, one without a secret.
        kc.add_identity_provider("google", display_name="Google")
        kc.add_identity_provider("facebook", display_name="Facebook", hide_on_login=True)
        kc.add_identity_provider("linkedin", display_name="LinkedIn", enabled=False)
        kc.add_identity_provider("apple", display_name="Apple", stored_value=None)
        # Enterprise platforms: one for each tenant's organization.
        kc.add_identity_provider("tenant1-sso", display_name="Tenant One SSO", organization_id=ORG_ID)
        kc.add_identity_provider("tenant2-sso", display_name="Tenant Two SSO", organization_id=OTHER_ORG_ID)

    def get_providers(self, token: str = SESSION_TOKEN) -> tuple[int, object]:
        return self.call("GET", PROVIDERS, None, self.bearer(token))

    def post_linked(self, payload: object = None, token: str = SESSION_TOKEN) -> tuple[int, object]:
        body = {"subject": SUBJECT} if payload is None else payload
        return self.post_json(LINKED, body, token)

    def assert_no_leak(self, body: object) -> None:
        text = json.dumps(body)
        for value in LEAKS:
            self.assertNotIn(value, text)


class LoginProvidersTest(LoginReadCase):
    def test_tenant_site_reads_its_platforms(self) -> None:
        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, body = self.get_providers()

        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {
                "providers": [
                    {"alias": "google", "display_name": "Google"},
                    {"alias": "tenant1-sso", "display_name": "Tenant One SSO"},
                ]
            },
        )
        audit = "\n".join(logs.output)
        self.assertIn("operation=list_login_providers", audit)
        self.assertIn("azp=site-tenant1-service", audit)
        self.assertIn("outcome=executed", audit)

    def test_other_tenant_sees_only_its_own_enterprise_platform(self) -> None:
        status, body = self.get_providers(OTHER_SITE_TOKEN)

        self.assertEqual(status, 200)
        self.assertEqual([row["alias"] for row in body["providers"]], ["google", "tenant2-sso"])
        self.assertNotIn("Tenant One SSO", json.dumps(body))

    def test_platform_without_a_secret_is_not_listed(self) -> None:
        kc = self.stack.keycloak
        # An empty secret and an unresolved setting placeholder are no secret either.
        kc.add_identity_provider("github", display_name="GitHub", stored_value="")
        kc.add_identity_provider("gitlab", display_name="GitLab", stored_value="${ATONOTA_GITLAB_CLIENT_SECRET}")

        _status, body = self.get_providers()

        aliases = [row["alias"] for row in body["providers"]]
        for missing in ("apple", "github", "gitlab"):
            self.assertNotIn(missing, aliases)

    def test_hidden_and_disabled_platforms_are_not_listed(self) -> None:
        _status, body = self.get_providers()

        aliases = [row["alias"] for row in body["providers"]]
        self.assertNotIn("facebook", aliases)
        self.assertNotIn("linkedin", aliases)

    def test_reply_is_built_from_an_allow_list(self) -> None:
        _status, body = self.get_providers()

        for row in body["providers"]:
            self.assertEqual(set(row), {"alias", "display_name"})
        self.assert_no_leak(body)

    def test_platform_without_a_display_name_shows_its_alias(self) -> None:
        self.stack.keycloak.add_identity_provider("microsoft")

        _status, body = self.get_providers()

        self.assertIn({"alias": "microsoft", "display_name": "microsoft"}, body["providers"])

    def test_alias_outside_the_panel_rule_is_not_listed(self) -> None:
        # The panel accepts `^[a-z0-9][a-z0-9_-]{0,63}$` only. A bad name would break its whole list.
        self.stack.keycloak.add_identity_provider("Bad Alias", display_name="Bad")

        _status, body = self.get_providers()

        self.assertNotIn("Bad", json.dumps(body))

    def test_long_display_name_is_cut_to_the_panel_limit(self) -> None:
        self.stack.keycloak.add_identity_provider("long", display_name="L" * 200)

        _status, body = self.get_providers()

        row = next(row for row in body["providers"] if row["alias"] == "long")
        self.assertEqual(len(row["display_name"]), 80)

    def test_only_tenant_site_clients_may_call(self) -> None:
        for token in (OPERATOR_TOKEN, PREVIEW_TOKEN, PRESS_TOKEN, "stranger-token"):
            with self.subTest(token=token):
                self.assertEqual(self.get_providers(token), (403, {"error": "forbidden"}))
        self.assertEqual(self.call("GET", PROVIDERS)[0], 401)

    def test_site_client_without_a_configured_tenant_is_forbidden(self) -> None:
        import dataclasses

        self.stack.app.settings = dataclasses.replace(self.stack.app.settings, tenants=self.stack.app.settings.tenants[:1])
        self.start_server(fake_verifier)

        self.assertEqual(self.get_providers(OTHER_SITE_TOKEN), (403, {"error": "forbidden"}))

    def test_keycloak_failure_is_an_upstream_failure(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/identity-provider/instances", (500, {"error": "internal http://keycloak:8080"}))

        status, body = self.get_providers()

        self.assertEqual((status, body), (502, {"error": "upstream_failed"}))

    def test_post_is_not_allowed(self) -> None:
        self.assertEqual(self.post_json(PROVIDERS, {}, SESSION_TOKEN)[0], 405)

    def test_the_platform_list_writes_nothing(self) -> None:
        self.get_providers()

        self.assertEqual(self.keycloak_writes(), [])


class LinkedAccountsTest(LoginReadCase):
    def setUp(self) -> None:
        super().setUp()
        kc = self.stack.keycloak
        kc.link_account(SUBJECT, "google", "ayse.ornek@elsewhere.example.test")
        # A link to a platform outside the tenant's list.
        kc.link_account(SUBJECT, "tenant2-sso", "ayse@tenant2.example")
        kc.add_credential(SUBJECT, "password", "My password")
        kc.add_credential(SUBJECT, "webauthn-passwordless", "Phone key")
        # A second factor is not a way to sign in on its own.
        kc.add_credential(SUBJECT, "otp", "Authenticator")

    def test_tenant_site_reads_the_accounts_of_its_member(self) -> None:
        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, body = self.post_linked()

        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {
                "providers": [
                    {"alias": "google", "display_name": "Google", "linked": True},
                    {"alias": "tenant1-sso", "display_name": "Tenant One SSO", "linked": False},
                ],
                "local_sign_in_methods": 2,
            },
        )
        audit = "\n".join(logs.output)
        self.assertIn("operation=list_linked_accounts", audit)
        self.assertIn("azp=site-tenant1-service", audit)
        self.assertIn("outcome=executed", audit)
        # The log names the endpoint, the caller and the result. It never names the person.
        for personal in (SUBJECT, "ayse", "elsewhere"):
            self.assertNotIn(personal, audit)

    def test_links_outside_the_tenant_list_are_left_out(self) -> None:
        _status, body = self.post_linked()

        self.assertNotIn("tenant2-sso", json.dumps(body))

    def test_reply_is_built_from_an_allow_list(self) -> None:
        _status, body = self.post_linked()

        self.assertEqual(set(body), {"providers", "local_sign_in_methods"})
        for row in body["providers"]:
            self.assertEqual(set(row), {"alias", "display_name", "linked"})
        self.assert_no_leak(body)
        for value in ("My password", "Phone key", "ayse.ornek@elsewhere.example.test", "argon2"):
            self.assertNotIn(value, json.dumps(body))

    def test_member_of_another_tenant_is_forbidden(self) -> None:
        self.stack.keycloak.link_account(OTHER_USER, "google", "ikinci@elsewhere.example.test")

        reply = self.post_linked({"subject": OTHER_USER})

        self.assertEqual(reply, (403, {"error": "forbidden"}))

    def test_unknown_user_gets_the_same_answer_as_a_stranger(self) -> None:
        unknown = self.post_linked({"subject": "00000000-0000-4000-8000-000000000000"})
        stranger = self.post_linked({"subject": OTHER_USER})

        self.assertEqual(unknown, (403, {"error": "forbidden"}))
        self.assertEqual(unknown, stranger)

    def test_other_tenant_cannot_read_a_member_of_this_tenant(self) -> None:
        self.assertEqual(self.post_linked(token=OTHER_SITE_TOKEN), (403, {"error": "forbidden"}))

    def test_only_tenant_site_clients_may_call(self) -> None:
        for token in (OPERATOR_TOKEN, PREVIEW_TOKEN, PRESS_TOKEN):
            with self.subTest(token=token):
                self.assertEqual(self.post_linked(token=token), (403, {"error": "forbidden"}))
        self.assertEqual(self.call("POST", LINKED, b'{"subject": "x"}')[0], 401)

    def test_execute_client_is_the_session_client(self) -> None:
        # The tenant site has one service client. It is in the execute and the session lists.
        self.assertEqual(self.post_linked(token=EXECUTE_TOKEN)[0], 200)

    def test_bad_request_bodies(self) -> None:
        for payload in (
            {},
            {"subject": ""},
            {"subject": 5},
            {"subject": "a/b"},
            {"subject": SUBJECT, "tenant": "tenant2"},
            {"subject": SUBJECT, "user": "x"},
            [SUBJECT],
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.post_linked(payload), (400, {"error": "bad_request"}))

    def test_keycloak_failure_is_an_upstream_failure(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users/{SUBJECT}/federated-identity", (500, None))

        self.assertEqual(self.post_linked(), (502, {"error": "upstream_failed"}))

    def test_linked_accounts_are_never_cached(self) -> None:
        self.assertEqual(self.post_linked()[1]["providers"][1]["linked"], False)
        self.stack.keycloak.link_account(SUBJECT, "tenant1-sso", "ayse@tenant1.example")

        self.assertEqual(self.post_linked()[1]["providers"][1]["linked"], True)

    def test_the_account_list_writes_nothing(self) -> None:
        self.post_linked()

        self.assertEqual(self.keycloak_writes(), [])


class CatalogCacheTest(unittest.TestCase):
    """The platform list is kept for a short time. Nothing else is kept (AJA-459)."""

    def setUp(self) -> None:
        self.now = 100.0
        self.loads = 0
        self.fail = False

    def load(self) -> tuple[login_reads.Platform, ...]:
        self.loads += 1
        if self.fail:
            raise TransportError("unexpected Keycloak response")
        return (login_reads.Platform("google", "Google"),)

    def cache(self) -> login_reads.CatalogCache:
        return login_reads.CatalogCache(self.load, seconds=30.0, clock=lambda: self.now)

    def test_a_second_read_within_the_window_does_not_load_again(self) -> None:
        cache = self.cache()
        cache.get()
        self.now += 29.9

        cache.get()

        self.assertEqual(self.loads, 1)

    def test_a_read_after_the_window_loads_again(self) -> None:
        cache = self.cache()
        cache.get()
        self.now += 30.0

        cache.get()

        self.assertEqual(self.loads, 2)

    def test_a_failed_load_is_not_kept(self) -> None:
        cache = self.cache()
        self.fail = True
        with self.assertRaises(TransportError):
            cache.get()
        self.fail = False

        self.assertEqual(cache.get(), (login_reads.Platform("google", "Google"),))
        self.assertEqual(self.loads, 2)

    def test_the_server_keeps_the_list_for_thirty_seconds(self) -> None:
        from identity_sync import server

        self.assertEqual(server.LOGIN_PROVIDER_CACHE_SECONDS, 30.0)
