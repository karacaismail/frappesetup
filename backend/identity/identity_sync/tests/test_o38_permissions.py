"""O-38: tenant approvals stay local; only operators access platform queues."""

import dataclasses
import unittest

from identity_sync.config import ConfigError, load_settings
from .test_config_cli import environment
from .test_server import ServerCase
from .fakes import ORG_ID

SITE = "site-kiraci1-service"
OTHER_SITE = "site-kiraci2-service"
OPERATOR = "identity-sync-operator"


class OperatorSettingsTest(unittest.TestCase):
    def env(self):
        return {**environment("http://keycloak.localhost", "http://press.localhost",
                              "http://tenant.localhost", ":memory:"),
                "IDENTITY_SYNC_EXECUTE_AZP": SITE,
                "IDENTITY_SYNC_SESSION_AZP": SITE,
                "IDENTITY_SYNC_OPERATOR_AZP": OPERATOR}

    def test_e2e_tenant_configuration_starts_with_separate_operator(self):
        settings = load_settings(self.env())
        self.assertEqual(settings.execute_azp, settings.session_azp)
        self.assertEqual(settings.operator_azp, frozenset({OPERATOR}))
        self.assertIn(OPERATOR, settings.known_azp)

    def test_operator_is_optional_and_defaults_to_empty(self):
        env = self.env()
        del env["IDENTITY_SYNC_OPERATOR_AZP"]
        self.assertFalse(load_settings(env).operator_azp)

    def test_tenant_lists_must_match(self):
        for name in ("EXECUTE", "SESSION"):
            with self.subTest(name=name), self.assertRaises(ConfigError):
                load_settings({**self.env(), f"IDENTITY_SYNC_{name}_AZP": ""})

    def test_reserved_site_namespace_is_refused_in_all_platform_lists(self):
        for name in ("OPERATOR", "PREVIEW", "DELETION"):
            for client in (SITE, "site-unregistered-service", "site-unregistered"):
                with self.subTest(name=name, client=client), self.assertRaises(ConfigError):
                    load_settings({**self.env(), f"IDENTITY_SYNC_{name}_AZP": client})

    def test_platform_lists_are_disjoint(self):
        for first, second in (("OPERATOR", "PREVIEW"), ("OPERATOR", "DELETION"), ("PREVIEW", "DELETION")):
            with self.subTest(first=first, second=second), self.assertRaises(ConfigError):
                load_settings({**self.env(), f"IDENTITY_SYNC_{first}_AZP": "shared-client",
                              f"IDENTITY_SYNC_{second}_AZP": "shared-client"})


class TenantOperatorHttpTest(ServerCase):
    two_tenants = True

    def setUp(self):
        super().setUp()
        settings = dataclasses.replace(self.stack.app.settings,
                                       execute_azp=frozenset({SITE, OTHER_SITE}),
                                       session_azp=frozenset({SITE, OTHER_SITE}),
                                       operator_azp=frozenset({OPERATOR}))
        self.stack.app.settings = settings
        self.start_server(lambda token: {"azp": token})
        kc = self.stack.keycloak
        kc.add_organization("other-org", "tenant2")
        kc.on("GET", f"{kc.admin}/users", (200, []))
        kc.on("POST", f"{kc.admin}/users", (201, None, {"Location": f"{kc.url}{kc.admin}/users/new-user"}))
        kc.on("POST", f"{kc.admin}/organizations/{ORG_ID}/members", (201, None))
        kc.on("PUT", f"{kc.admin}/users/new-user/execute-actions-email", (204, None))

    def test_tenant2_replay_is_403_before_any_write(self):
        before = self.downstream_writes()
        for dry_run in (True, False):
            self.assertEqual(self.post_json("/v1/dead-letters/replay", {"dry_run": dry_run}, OTHER_SITE)[0], 403)
        self.assertEqual(self.downstream_writes(), before)

    def test_tenant1_invites_into_own_organization_after_approval(self):
        invitation = {"email": "invited@example.test", "organization_id": ORG_ID}
        status, preview = self.post_json("/v1/invitations", {**invitation, "dry_run": True}, SITE)
        self.assertEqual(status, 200)
        status, _ = self.post_json("/v1/invitations", {**invitation, "dry_run": False,
                                   "preview_digest": preview["preview_digest"], "approval_id": "own-invite"}, SITE)
        self.assertEqual(status, 200)
        self.assertEqual(len(self.keycloak_writes()), 3)

    def test_tenant1_cannot_invite_into_another_organization(self):
        for dry_run in (True, False):
            body = {"email": "invited@example.test", "organization_id": "other-org", "dry_run": dry_run,
                    "preview_digest": "0" * 64, "approval_id": "other-invite"}
            self.assertEqual(self.post_json("/v1/invitations", body, SITE)[0], 403)
        self.assertEqual(self.keycloak_writes(), [])

    def test_only_operator_can_access_platform_routes(self):
        routes = (("GET", "/v1/dead-letters"), ("GET", "/v1/operations"),
                  ("POST", "/v1/reconcile"), ("POST", "/v1/dead-letters/replay"))
        for method, path in routes:
            for client in (SITE, OTHER_SITE, "ai-agent", "press-service"):
                with self.subTest(path=path, client=client):
                    result = (self.call(method, path, headers=self.bearer(client)) if method == "GET"
                              else self.post_json(path, {"dry_run": True}, client))
                    self.assertEqual(result[0], 403)
        self.assertEqual(self.call("GET", "/v1/operations", headers=self.bearer(OPERATOR))[0], 200)
        self.assertEqual(self.post_json("/v1/dead-letters/replay", {"dry_run": True}, OPERATOR)[0], 200)

    def test_resolve_is_bound_to_recorded_organization(self):
        store = self.stack.app.store
        store.operation_begin("own-job", "invite_user", ORG_ID, ["create_user"])
        store.operation_begin("other-job", "invite_user", "other-org", ["create_user"])
        for job, client in (("other-job", SITE), ("own-job", OTHER_SITE), ("own-job", OPERATOR)):
            with self.subTest(job=job, client=client):
                self.assertEqual(self.post_json(f"/v1/operations/{job}/resolve", {"resolution": "completed"}, client)[0], 403)
        self.assertEqual(len(store.operations()), 2)
        self.assertEqual(self.post_json("/v1/operations/own-job/resolve", {"resolution": "completed"}, SITE)[0], 200)
        self.assertEqual([row["operation_id"] for row in store.operations()], ["other-job"])
