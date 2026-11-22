"""Keycloak Admin API istemcisinin testleri.

Yolların kaynağı Keycloak 26.8.2 Admin REST API belgesidir.
İstemci ayarlarının kaynağı `docs/sozlesmeler.md` dosyasının 2. bölümüdür.
"""

from __future__ import annotations

import unittest

from identity_sync.httpjson import HttpError
from identity_sync.keycloak_admin import KeycloakAdmin
from identity_sync.mapping import Organization
from identity_sync.tokens import TokenProvider

from . import fakes
from .fakes import ORG_ID, SUBJECT, FakeKeycloak, keycloak_user

CLIENT_UUID = "44444444-4444-4444-8444-444444444444"
TENANT_URL = "http://kiraci2.localhost:6111"


class AdminCase(unittest.TestCase):
    def setUp(self) -> None:
        self.kc = FakeKeycloak()
        self.addCleanup(self.kc.close)
        tokens = TokenProvider(
            f"{self.kc.url}/realms/platform/protocol/openid-connect/token",
            "identity-sync",
            "test-client-secret",
            timeout=5,
        )
        self.admin = KeycloakAdmin(self.kc.url, "platform", tokens, admin_scope="admin-api", timeout=5)
        self.base = self.kc.admin

    def writes(self) -> list[fakes.Recorded]:
        return [r for r in self.kc.requests if r.method != "GET" and "/admin/" in r.path]


class ReadTest(AdminCase):
    def test_snapshot_joins_user_and_organizations(self) -> None:
        self.kc.add_user(keycloak_user(), [{"id": ORG_ID, "name": "Kiracı 1", "alias": "kiraci1"}])

        snapshot = self.admin.get_user_snapshot(SUBJECT)

        self.assertEqual(snapshot.subject, SUBJECT)
        self.assertEqual(snapshot.email, "ayse@example.test")
        self.assertTrue(snapshot.email_verified)
        self.assertTrue(snapshot.enabled)
        self.assertEqual(snapshot.organizations, (Organization(id=ORG_ID, alias="kiraci1"),))

    def test_missing_user_gives_none(self) -> None:
        self.kc.remove_user(SUBJECT)

        self.assertIsNone(self.admin.get_user_snapshot(SUBJECT))

    def test_404_without_working_realm_is_an_error(self) -> None:
        self.kc.on("GET", f"{self.base}/users/count", (404, None))

        with self.assertRaises(HttpError):
            self.admin.get_user(SUBJECT)

    def test_dot_segments_are_never_sent(self) -> None:
        for bad in ("..", ".", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.admin.get_user(bad)
        self.assertEqual(self.kc.requests, [])

    def test_missing_organization_gives_none(self) -> None:
        self.kc.on("GET", f"{self.base}/organizations/{ORG_ID}", (404, {"error": "Organization not found."}))

        self.assertIsNone(self.admin.get_organization(ORG_ID))

    def test_server_error_is_raised_not_hidden(self) -> None:
        self.kc.on("GET", f"{self.base}/users/{SUBJECT}", (500, None))

        with self.assertRaises(HttpError) as caught:
            self.admin.get_user(SUBJECT)
        self.assertEqual(caught.exception.status, 500)

    def test_list_users_reads_every_page(self) -> None:
        pages = {"0": [keycloak_user(subject=f"u-{n}") for n in range(100)], "100": [keycloak_user(subject="u-son")]}
        self.kc.on("GET", f"{self.base}/users", lambda req: (200, pages.get(req.query["first"][0], [])))

        users = list(self.admin.list_users())

        self.assertEqual(len(users), 101)
        self.assertEqual(users[-1]["id"], "u-son")
        self.assertEqual(self.kc.calls("GET", f"{self.base}/users")[0].query["max"], ["100"])


class OrganizationTest(AdminCase):
    def test_create_organization_returns_new_id(self) -> None:
        self.kc.on(
            "POST",
            f"{self.base}/organizations",
            (201, None, {"Location": f"{self.kc.url}{self.base}/organizations/{ORG_ID}"}),
        )

        outcome = self.admin.create_organization("kiraci2", "Kiracı 2")

        self.assertTrue(outcome.executed)
        self.assertEqual(outcome.value, ORG_ID)
        self.assertEqual(self.writes()[0].json(), {"name": "Kiracı 2", "alias": "kiraci2", "enabled": True})

    def test_create_organization_dry_run_sends_nothing(self) -> None:
        outcome = self.admin.create_organization("kiraci2", "Kiracı 2", dry_run=True)

        self.assertFalse(outcome.executed)
        self.assertEqual(outcome.preview.operation, "keycloak.create_organization")
        self.assertEqual(outcome.preview.target, "kiraci2")
        self.assertFalse(outcome.preview.destructive)
        self.assertEqual(self.kc.requests, [])

    def test_add_member_sends_user_id_as_json_string(self) -> None:
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))

        self.admin.add_organization_member(ORG_ID, SUBJECT)

        self.assertEqual(self.writes()[0].json(), SUBJECT)

    def test_add_member_twice_is_not_an_error(self) -> None:
        # Keycloak üye zaten varsa 409 döner. İşlem tekrar edilebilir olmalıdır.
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (409, {"errorMessage": "exists"}))

        outcome = self.admin.add_organization_member(ORG_ID, SUBJECT)

        self.assertTrue(outcome.executed)

    def test_ensure_organization_reuses_existing_one(self) -> None:
        self.kc.on("GET", f"{self.base}/organizations", (200, [{"id": ORG_ID, "name": "x", "alias": "kiraci2"}]))
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))

        org_id = self.admin.ensure_organization_with_member("kiraci2", "Kiracı 2", SUBJECT)

        self.assertEqual(org_id, ORG_ID)
        self.assertEqual(self.kc.calls("POST", f"{self.base}/organizations"), [])
        search = self.kc.calls("GET", f"{self.base}/organizations")[0]
        # Keycloak arama ucu ada bakar, takma ada bakmaz (OrganizationsResource.java).
        self.assertEqual(search.query["search"], ["Kiracı 2"])
        self.assertEqual(search.query["exact"], ["true"])

    def test_ensure_organization_ignores_similar_alias(self) -> None:
        self.kc.on("GET", f"{self.base}/organizations", (200, [{"id": "baska", "name": "Kiracı 2", "alias": "kiraci20"}]))
        self.kc.on(
            "POST",
            f"{self.base}/organizations",
            (201, None, {"Location": f"{self.kc.url}{self.base}/organizations/{ORG_ID}"}),
        )
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))

        self.assertEqual(self.admin.ensure_organization_with_member("kiraci2", "Kiracı 2", SUBJECT), ORG_ID)


class InviteTest(AdminCase):
    def test_execute_actions_email(self) -> None:
        self.kc.on("PUT", f"{self.base}/users/{SUBJECT}/execute-actions-email", (204, None))

        self.admin.send_execute_actions_email(
            SUBJECT, ("UPDATE_PASSWORD", "CONFIGURE_TOTP"), client_id="press", lifespan=86400
        )

        (sent,) = self.writes()
        self.assertEqual(sent.method, "PUT")
        self.assertEqual(sent.json(), ["UPDATE_PASSWORD", "CONFIGURE_TOTP"])
        self.assertEqual(sent.query, {"client_id": ["press"], "lifespan": ["86400"]})

    def test_invite_creates_user_adds_member_and_sends_email(self) -> None:
        self.kc.on("GET", f"{self.base}/users", (200, []))
        self.kc.on(
            "POST", f"{self.base}/users", (201, None, {"Location": f"{self.kc.url}{self.base}/users/{SUBJECT}"})
        )
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))
        self.kc.on("PUT", f"{self.base}/users/{SUBJECT}/execute-actions-email", (204, None))

        result = self.admin.invite_user("davetli@example.test", "Deniz", "Örnek", ORG_ID)

        self.assertEqual(result.subject, SUBJECT)
        self.assertEqual(
            [p.operation for p in result.previews],
            ["keycloak.create_user", "keycloak.add_organization_member", "keycloak.send_execute_actions_email"],
        )
        created = self.kc.calls("POST", f"{self.base}/users")[0].json()
        self.assertEqual(
            created,
            {
                "username": "davetli@example.test",
                "email": "davetli@example.test",
                "firstName": "Deniz",
                "lastName": "Örnek",
                "enabled": True,
                "emailVerified": False,
            },
        )
        (email,) = self.kc.calls("PUT", f"{self.base}/users/{SUBJECT}/execute-actions-email")
        # Davet eylemleri karar sitesinden gelir: UPDATE_PASSWORD ve CONFIGURE_TOTP.
        self.assertEqual(email.json(), ["UPDATE_PASSWORD", "CONFIGURE_TOTP"])

    def test_invite_reuses_existing_user(self) -> None:
        self.kc.on("GET", f"{self.base}/users", (200, [keycloak_user(email="davetli@example.test")]))
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))
        self.kc.on("PUT", f"{self.base}/users/{SUBJECT}/execute-actions-email", (204, None))

        result = self.admin.invite_user("davetli@example.test", "Deniz", "Örnek", ORG_ID)

        self.assertEqual(result.subject, SUBJECT)
        self.assertEqual(self.kc.calls("POST", f"{self.base}/users"), [])
        lookup = self.kc.calls("GET", f"{self.base}/users")[0]
        self.assertEqual(lookup.query["email"], ["davetli@example.test"])
        self.assertEqual(lookup.query["exact"], ["true"])

    def test_invite_dry_run_only_reads(self) -> None:
        self.kc.on("GET", f"{self.base}/users", (200, []))

        result = self.admin.invite_user("davetli@example.test", "Deniz", "Örnek", ORG_ID, dry_run=True)

        self.assertIsNone(result.subject)
        self.assertEqual(len(result.previews), 3)
        self.assertEqual(self.writes(), [])
        self.assertNotIn("davetli@example.test", " ".join(p.summary for p in result.previews))


class SiteClientTest(AdminCase):
    def test_creates_confidential_client_with_exact_urls(self) -> None:
        found: list[object] = []
        self.kc.on("GET", f"{self.base}/clients", lambda _r: (200, list(found)))

        def create(req: fakes.Recorded) -> fakes.Reply:
            found.append({"id": CLIENT_UUID, "clientId": "site-kiraci2"})
            return 201, None, {"Location": f"{self.kc.url}{self.base}/clients/{CLIENT_UUID}"}

        self.kc.on("POST", f"{self.base}/clients", create)
        self.kc.on("GET", f"{self.base}/clients/{CLIENT_UUID}/client-secret", (200, {"type": "secret", "value": "s3"}))

        site = self.admin.ensure_site_client("kiraci2", TENANT_URL)

        self.assertEqual(site.client_id, "site-kiraci2")
        self.assertEqual(site.client_secret, "s3")
        body = self.kc.calls("POST", f"{self.base}/clients")[0].json()
        self.assertEqual(body["clientId"], "site-kiraci2")
        self.assertEqual(body["protocol"], "openid-connect")
        self.assertFalse(body["publicClient"])
        self.assertTrue(body["standardFlowEnabled"])
        self.assertFalse(body["implicitFlowEnabled"])
        self.assertFalse(body["directAccessGrantsEnabled"])
        self.assertFalse(body["serviceAccountsEnabled"])
        # Dönüş adresi tam adrestir. Joker karakter yoktur.
        self.assertEqual(
            body["redirectUris"],
            [f"{TENANT_URL}/api/method/frappe.integrations.oauth2_logins.login_via_keycloak"],
        )
        self.assertEqual(
            body["attributes"],
            {
                "backchannel.logout.url": f"{TENANT_URL}/api/method/platform_core.api.keycloak_backchannel_logout",
                "backchannel.logout.session.required": "true",
            },
        )

    def test_existing_client_is_not_created_again(self) -> None:
        self.kc.on("GET", f"{self.base}/clients", (200, [{"id": CLIENT_UUID, "clientId": "site-kiraci2"}]))
        self.kc.on("GET", f"{self.base}/clients/{CLIENT_UUID}/client-secret", (200, {"type": "secret", "value": "s3"}))

        site = self.admin.ensure_site_client("kiraci2", TENANT_URL)

        self.assertEqual(site.client_secret, "s3")
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.kc.calls("GET", f"{self.base}/clients")[0].query["clientId"], ["site-kiraci2"])

    def test_secret_is_not_shown_in_repr(self) -> None:
        self.kc.on("GET", f"{self.base}/clients", (200, [{"id": CLIENT_UUID, "clientId": "site-kiraci2"}]))
        self.kc.on("GET", f"{self.base}/clients/{CLIENT_UUID}/client-secret", (200, {"value": "cok-gizli"}))

        site = self.admin.ensure_site_client("kiraci2", TENANT_URL)

        self.assertNotIn("cok-gizli", repr(site))

    def test_rejects_bad_tenant_name(self) -> None:
        for bad in ("", "Kiraci", "a/b", "a b", "-a", "x" * 41):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.admin.ensure_site_client(bad, TENANT_URL)
        self.assertEqual(self.kc.requests, [])


if __name__ == "__main__":
    unittest.main()
