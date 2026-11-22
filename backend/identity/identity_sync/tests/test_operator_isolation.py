"""The handoff requires platform administration to use a separate operator client."""

from identity_sync.config import ConfigError, load_settings

from .test_config_cli import environment
from .test_server import ServerCase, SESSION_TOKEN


class OperatorIsolationTest(ServerCase):
    def test_tenant_cannot_read_preview_or_execute_platform_operations(self):
        before = self.downstream_writes()
        routes = (
            ("GET", "/v1/dead-letters", None),
            ("GET", "/v1/operations", None),
            ("POST", "/v1/reconcile", {"dry_run": True}),
            ("POST", "/v1/reconcile", {"dry_run": False}),
            ("POST", "/v1/dead-letters/replay", {"dry_run": True}),
            ("POST", "/v1/dead-letters/replay", {"dry_run": False}),
            ("POST", "/v1/invitations", {"dry_run": True}),
            ("POST", "/v1/operations/o-1/resolve", {"resolution": "abandoned"}),
        )
        for method, path, body in routes:
            with self.subTest(path=path, body=body):
                if method == "GET":
                    status, _ = self.call(method, path, headers=self.bearer(SESSION_TOKEN))
                else:
                    status, _ = self.post_json(path, body, SESSION_TOKEN)
                self.assertEqual(status, 403)
        self.assertEqual(self.downstream_writes(), before)

    def test_operator_settings_are_separate_from_tenant_settings(self):
        settings = load_settings({**environment("http://keycloak.localhost", "http://press.localhost", "http://tenant.localhost", ":memory:"), "IDENTITY_SYNC_EXECUTE_AZP": "identity-sync-operator"})
        self.assertEqual(settings.execute_azp, frozenset({"identity-sync-operator"}))
        self.assertEqual(settings.session_azp, frozenset({"site-kiraci1-service"}))

    def test_tenant_cannot_be_configured_as_operator_or_preview(self):
        for name in ("EXECUTE", "PREVIEW"):
            for client in ("site-kiraci1-service", "site-unregistered-service"):
                with self.subTest(name=name, client=client), self.assertRaises(ConfigError):
                    load_settings({**environment("http://keycloak.localhost", "http://press.localhost", "http://tenant.localhost", ":memory:"), "IDENTITY_SYNC_EXECUTE_AZP": "identity-sync-operator",
                                   f"IDENTITY_SYNC_{name}_AZP": client})
