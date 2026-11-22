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
TENANT_URL = "http://tenant2.localhost:6111"


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
        self.admin = KeycloakAdmin(self.kc.url, "platform", tokens, admin_scope=fakes.ADMIN_SCOPE, timeout=5)
        self.base = self.kc.admin

    def writes(self) -> list[fakes.Recorded]:
        return [r for r in self.kc.requests if r.method != "GET" and "/admin/" in r.path]


class ReadTest(AdminCase):
    def test_snapshot_joins_user_and_organizations(self) -> None:
        self.kc.add_user(keycloak_user(), [{"id": ORG_ID, "name": "Kiracı 1", "alias": "tenant1"}])

        snapshot = self.admin.get_user_snapshot(SUBJECT)

        self.assertEqual(snapshot.subject, SUBJECT)
        self.assertEqual(snapshot.email, "ayse@example.test")
        self.assertTrue(snapshot.email_verified)
        self.assertTrue(snapshot.enabled)
        self.assertEqual(snapshot.organizations, (Organization(id=ORG_ID, alias="tenant1", name="Kiracı 1"),))

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

        outcome = self.admin.create_organization("tenant2", "Kiracı 2")

        self.assertTrue(outcome.executed)
        self.assertEqual(outcome.value, ORG_ID)
        self.assertEqual(self.writes()[0].json(), {"name": "Kiracı 2", "alias": "tenant2", "enabled": True})

    def test_create_organization_dry_run_sends_nothing(self) -> None:
        outcome = self.admin.create_organization("tenant2", "Kiracı 2", dry_run=True)

        self.assertFalse(outcome.executed)
        self.assertEqual(outcome.preview.operation, "keycloak.create_organization")
        self.assertEqual(outcome.preview.target, "tenant2")
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

    def test_find_organization_searches_by_name_and_checks_the_alias(self) -> None:
        self.kc.on("GET", f"{self.base}/organizations", (200, [{"id": ORG_ID, "name": "Kiracı 2", "alias": "tenant2"}]))

        self.assertEqual(self.admin.find_organization("Kiracı 2", "tenant2").id, ORG_ID)
        search = self.kc.calls("GET", f"{self.base}/organizations")[0]
        # Keycloak's search looks at the name, not the alias (OrganizationsResource.java).
        self.assertEqual(search.query["search"], ["Kiracı 2"])
        self.assertEqual(search.query["exact"], ["true"])

    def test_find_organization_ignores_a_similar_alias(self) -> None:
        self.kc.on("GET", f"{self.base}/organizations", (200, [{"id": "baska", "name": "Kiracı 2", "alias": "tenant20"}]))

        self.assertIsNone(self.admin.find_organization("Kiracı 2", "tenant2"))

    def test_join_adds_the_member_to_exactly_the_planned_organization(self) -> None:
        # The plan named the organization by its id. No new lookup may pick another target.
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))

        self.admin.ensure_organization_member("tenant2", "Kiracı 2", SUBJECT, ORG_ID)

        self.assertEqual([(r.method, r.path) for r in self.kc.requests if "/admin/" in r.path],
                         [("POST", f"{self.base}/organizations/{ORG_ID}/members")])

    def test_create_makes_a_new_organization_then_adds_the_member(self) -> None:
        self.kc.on(
            "POST", f"{self.base}/organizations", (201, None, {"Location": f"{self.kc.url}{self.base}/organizations/{ORG_ID}"})
        )
        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (201, None))

        self.admin.ensure_organization_member("tenant2", "Kiracı 2", SUBJECT, None)

        self.assertEqual([r.path for r in self.writes()],
                         [f"{self.base}/organizations", f"{self.base}/organizations/{ORG_ID}/members"])

    def test_create_fails_when_the_organization_appeared_meanwhile(self) -> None:
        # The plan said "create". Keycloak now has that name. The member is not added to the other one.
        self.kc.on("POST", f"{self.base}/organizations", (409, {"errorMessage": "exists"}))

        with self.assertRaises(HttpError):
            self.admin.ensure_organization_member("tenant2", "Kiracı 2", SUBJECT, None)
        self.assertEqual(len(self.writes()), 1)


class SessionTest(AdminCase):
    """Source: Keycloak 26.8 Admin REST API, DELETE /admin/realms/{realm}/sessions/{session}."""

    SID = "55555555-5555-4555-8555-555555555555"

    def test_delete_session(self) -> None:
        self.kc.on("DELETE", f"{self.base}/sessions/{self.SID}", (204, None))

        self.admin.delete_session(self.SID)

        (call,) = self.kc.calls("DELETE", f"{self.base}/sessions/{self.SID}")
        self.assertEqual(call.headers["authorization"], f"Bearer token-for:{fakes.ADMIN_SCOPE}")

    def test_session_that_is_already_gone_is_fine(self) -> None:
        # Repeatable: Keycloak answers 404 for a closed session. The realm itself answers.
        self.kc.on("DELETE", f"{self.base}/sessions/{self.SID}", (404, {"error": "Session not found"}))

        self.admin.delete_session(self.SID)

    def test_404_from_a_wrong_address_is_not_taken_as_closed(self) -> None:
        self.kc.on("DELETE", f"{self.base}/sessions/{self.SID}", (404, None))
        self.kc.on("GET", f"{self.base}/users/count", (404, None))

        with self.assertRaises(HttpError):
            self.admin.delete_session(self.SID)

    def test_refusal_is_raised(self) -> None:
        self.kc.on("DELETE", f"{self.base}/sessions/{self.SID}", (403, None))

        with self.assertRaises(HttpError):
            self.admin.delete_session(self.SID)

    def test_path_segments_are_never_sent(self) -> None:
        for bad in ("..", ".", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.admin.delete_session(bad)
        self.assertEqual(self.kc.requests, [])


class RolesTest(AdminCase):
    """The fake follows the roles in docs/sozlesmeler.md, section 2."""

    def test_token_without_admin_scope_is_refused(self) -> None:
        tokens = TokenProvider(
            f"{self.kc.url}/realms/platform/protocol/openid-connect/token", "identity-sync", "test-client-secret", timeout=5
        )
        for scope in ("", "aud-site-tenant1", "aud-press", "admin-api"):
            with self.subTest(scope=scope):
                admin = KeycloakAdmin(self.kc.url, "platform", tokens, admin_scope=scope, timeout=5)
                with self.assertRaises(HttpError) as caught:
                    admin.get_user(SUBJECT)
                self.assertEqual(caught.exception.status, 403)

    def test_service_does_not_administer_keycloak_clients(self) -> None:
        # docs/sozlesmeler.md, section 7: identity-sync opens no client in Keycloak and its
        # service account has no `manage-clients` role. The kimlik-realm job opens tenant clients.
        import inspect

        from identity_sync import keycloak_admin

        for name in ("ensure_site_client", "create_site_client", "find_client", "get_client_secret"):
            self.assertFalse(hasattr(KeycloakAdmin, name), name)
        self.assertFalse(hasattr(keycloak_admin, "SiteClient"))
        source = inspect.getsource(keycloak_admin)
        self.assertNotIn('"/clients', source)
        self.assertNotIn("client-secret", source)


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

    def test_invite_refuses_when_plan_differs_from_the_approved_one(self) -> None:
        # Onay "yeni kullanıcı aç" planını gösterdi. Kullanıcı arada açıldı. Plan artık farklıdır.
        from identity_sync.keycloak_admin import PlanChanged

        self.kc.on("GET", f"{self.base}/users", (200, []))
        approved = self.admin.invite_user("davetli@example.test", "Deniz", "Örnek", ORG_ID, dry_run=True).previews
        self.kc.on("GET", f"{self.base}/users", (200, [keycloak_user(email="davetli@example.test")]))

        with self.assertRaises(PlanChanged):
            self.admin.invite_user("davetli@example.test", "Deniz", "Örnek", ORG_ID, expected_previews=approved)
        self.assertEqual(self.writes(), [])

    def test_unexpected_success_codes_are_not_accepted(self) -> None:
        from identity_sync.httpjson import TransportError

        self.kc.on("POST", f"{self.base}/organizations/{ORG_ID}/members", (202, None))
        self.kc.on("PUT", f"{self.base}/users/{SUBJECT}/execute-actions-email", (202, None))
        self.kc.on("POST", f"{self.base}/organizations", (200, None, {"Location": f"{self.kc.url}{self.base}/organizations/x"}))

        with self.assertRaises(TransportError):
            self.admin.add_organization_member(ORG_ID, SUBJECT)
        with self.assertRaises(TransportError):
            self.admin.send_execute_actions_email(SUBJECT, ("UPDATE_PASSWORD",))
        with self.assertRaises(TransportError):
            self.admin.create_organization("tenant2", "Kiracı 2")

    def test_invite_dry_run_only_reads(self) -> None:
        self.kc.on("GET", f"{self.base}/users", (200, []))

        result = self.admin.invite_user("davetli@example.test", "Deniz", "Örnek", ORG_ID, dry_run=True)

        self.assertIsNone(result.subject)
        self.assertEqual(len(result.previews), 3)
        self.assertEqual(self.writes(), [])
        self.assertNotIn("davetli@example.test", " ".join(p.summary for p in result.previews))
