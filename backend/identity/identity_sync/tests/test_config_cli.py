"""Ayar okumanın ve komut satırının testleri."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from identity_sync import cli
from identity_sync.config import ConfigError, load_settings

from . import fakes
from .fakes import ORG_ID, SUBJECT, FakeKeycloak, FakeSite, keycloak_user


def environment(keycloak: str, press: str, tenant: str, db: str) -> dict[str, str]:
    return {
        "IDENTITY_SYNC_KEYCLOAK_PUBLIC_URL": keycloak,
        "IDENTITY_SYNC_CLIENT_SECRET": "test-client-secret",
        "IDENTITY_SYNC_PRESS_URL": press,
        "IDENTITY_SYNC_TENANTS": json.dumps([{"name": "kiraci1", "base_url": tenant, "organization": "kiraci1"}]),
        "IDENTITY_SYNC_WEBHOOK_SECRET": "test-webhook-secret",
        "IDENTITY_SYNC_DB": db,
    }


class ConfigTest(unittest.TestCase):
    ENV = environment("http://kimlik.localhost:6110/", "http://press.localhost:6113", "http://kiraci1.localhost:6111", "/tmp/x.sqlite3")

    def test_defaults_follow_the_shared_contract(self) -> None:
        settings = load_settings(self.ENV)

        self.assertEqual(settings.realm, "platform")
        self.assertEqual(settings.client_id, "identity-sync")
        self.assertEqual(settings.issuer, "http://kimlik.localhost:6110/realms/platform")
        self.assertEqual(settings.keycloak_base_url, "http://kimlik.localhost:6110")
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.tenants[0].name, "kiraci1")

    def test_internal_url_is_used_for_calls_but_not_for_issuer(self) -> None:
        settings = load_settings({**self.ENV, "IDENTITY_SYNC_KEYCLOAK_INTERNAL_URL": "http://keycloak:8080"})

        self.assertEqual(settings.keycloak_base_url, "http://keycloak:8080")
        self.assertEqual(settings.issuer, "http://kimlik.localhost:6110/realms/platform")

    def test_missing_values_are_listed_by_name(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            load_settings({})
        message = str(caught.exception)
        for name in ("IDENTITY_SYNC_KEYCLOAK_PUBLIC_URL", "IDENTITY_SYNC_CLIENT_SECRET", "IDENTITY_SYNC_WEBHOOK_SECRET"):
            self.assertIn(name, message)

    def test_error_never_shows_secret_values(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            load_settings({**self.ENV, "IDENTITY_SYNC_TENANTS": "bozuk"})
        self.assertNotIn("test-client-secret", str(caught.exception))

    def test_repr_hides_secrets(self) -> None:
        text = repr(load_settings(self.ENV))
        self.assertNotIn("test-client-secret", text)
        self.assertNotIn("test-webhook-secret", text)

    def test_rejects_bad_tenant_and_url(self) -> None:
        bad_values = (
            {"IDENTITY_SYNC_TENANTS": json.dumps([{"name": "Kiraci 1", "base_url": "http://x.test", "organization": "k"}])},
            {"IDENTITY_SYNC_TENANTS": json.dumps([{"name": "k", "base_url": "ftp://x.test", "organization": "k"}])},
            {"IDENTITY_SYNC_PRESS_URL": "press.localhost"},
            {"IDENTITY_SYNC_PORT": "abc"},
        )
        for change in bad_values:
            with self.subTest(change=change), self.assertRaises(ConfigError):
                load_settings({**self.ENV, **change})


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.keycloak, self.press, self.tenant = FakeKeycloak(), FakeSite(), FakeSite()
        for server in (self.keycloak, self.press, self.tenant):
            self.addCleanup(server.close)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.env = environment(
            self.keycloak.url, self.press.url, self.tenant.url, os.path.join(self.dir.name, "db.sqlite3")
        )
        self.org = {"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}
        self.keycloak.add_user(keycloak_user(), [self.org])

    def run_cli(self, *args: str) -> tuple[int, object]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(args), env=self.env)
        return code, json.loads(out.getvalue())

    def queue_failed_event(self) -> None:
        from identity_sync.app import build_app
        from identity_sync.events import Event

        self.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        app = build_app(load_settings(self.env), sleep=lambda _s: None)
        app.processor.handle(Event(id="e-1", kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=SUBJECT))
        app.close()
        self.tenant.on("POST", fakes.TENANT_PROVISION, (200, {"message": {"ok": True}}))

    def test_dead_letters_lists_queue(self) -> None:
        self.queue_failed_event()

        code, body = self.run_cli("dead-letters")

        self.assertEqual(code, 0)
        self.assertEqual(body["dead_letters"][0]["event"]["id"], "e-1")

    def test_replay_dry_run_keeps_queue(self) -> None:
        self.queue_failed_event()

        code, body = self.run_cli("replay-dead-letters", "--dry-run")

        self.assertEqual((code, body["results"][0]["status"]), (0, "preview"))
        self.assertEqual(self.run_cli("dead-letters")[1]["dead_letters"][0]["attempts"], 1)

    def test_replay_empties_queue(self) -> None:
        self.queue_failed_event()

        code, body = self.run_cli("replay-dead-letters")

        self.assertEqual((code, body["results"][0]["status"]), (0, "processed"))
        self.assertEqual(self.run_cli("dead-letters")[1], {"dead_letters": []})

    def test_replay_fails_when_event_still_fails(self) -> None:
        self.queue_failed_event()
        self.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))

        code, _body = self.run_cli("replay-dead-letters")

        self.assertEqual(code, 1)

    def test_reconcile_reports_and_only_reads(self) -> None:
        kc = self.keycloak
        kc.on("GET", f"{kc.admin}/organizations", lambda r: (200, [self.org] if r.query["first"] == ["0"] else []))
        kc.on(
            "GET",
            f"{kc.admin}/organizations/{ORG_ID}/members",
            lambda r: (200, [keycloak_user()] if r.query["first"] == ["0"] else []),
        )
        issuer = f"{kc.url}/realms/platform"
        row = {"issuer": issuer, "subject": SUBJECT, "email": "ayse@example.test", "enabled": True}
        self.press.on("GET", fakes.PRESS_LIST, (200, {"message": [row]}))
        self.tenant.on("GET", fakes.TENANT_LIST, (200, {"message": []}))

        code, body = self.run_cli("reconcile")

        self.assertEqual(code, 1)
        self.assertEqual(body, {"count": 1, "differences": [{"target": "kiraci1", "subject": SUBJECT, "kind": "missing"}]})
        self.assertEqual(self.press.writes() + self.tenant.writes(), [])
        self.assertEqual([r for r in kc.requests if r.method != "GET" and "/admin/" in r.path], [])

    def test_reconcile_without_difference_exits_zero(self) -> None:
        kc = self.keycloak
        kc.on("GET", f"{kc.admin}/organizations", (200, []))
        self.press.on("GET", fakes.PRESS_LIST, (200, {"message": []}))
        self.tenant.on("GET", fakes.TENANT_LIST, (200, {"message": []}))

        self.assertEqual(self.run_cli("reconcile"), (0, {"count": 0, "differences": []}))

    def test_missing_settings_exit_with_two(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["reconcile"], env={})
        self.assertEqual(code, 2)
        self.assertIn("IDENTITY_SYNC_CLIENT_SECRET", err.getvalue())


if __name__ == "__main__":
    unittest.main()
