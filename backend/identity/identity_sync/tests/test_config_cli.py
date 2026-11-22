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
from .fakes import ORG_ID, SUBJECT, FakeKeycloak, FakePress, FakeTenant, keycloak_user


def environment(keycloak: str, press: str, tenant: str, db: str) -> dict[str, str]:
    return {
        "IDENTITY_SYNC_KEYCLOAK_PUBLIC_URL": keycloak,
        "IDENTITY_SYNC_CLIENT_SECRET": "test-client-secret",
        "IDENTITY_SYNC_PRESS_URL": press,
        "IDENTITY_SYNC_TENANTS": json.dumps([{"name": "kiraci1", "base_url": tenant, "organization": "kiraci1"}]),
        "IDENTITY_SYNC_WEBHOOK_SECRET": "test-webhook-secret",
        "IDENTITY_SYNC_DB": db,
        "IDENTITY_SYNC_DIGEST_KEY": "test-digest-key-0123456789",
        "IDENTITY_SYNC_REALM_ID": fakes.REALM_ID,
        "IDENTITY_SYNC_EXECUTE_AZP": "approval-service",
        "IDENTITY_SYNC_PREVIEW_AZP": "ai-agent, ops-bff",
        "IDENTITY_SYNC_SESSION_AZP": "site-kiraci1",
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
        self.assertEqual(settings.realm_id, fakes.REALM_ID)

    def test_execute_and_preview_clients_are_separate_lists(self) -> None:
        settings = load_settings(self.ENV)

        self.assertEqual(settings.execute_azp, frozenset({"approval-service"}))
        self.assertEqual(settings.preview_azp, frozenset({"ai-agent", "ops-bff"}))

    def test_admin_scope_defaults_to_the_contract_value(self) -> None:
        # docs/sozlesmeler.md, section 2: the Admin API token is requested with this scope.
        self.assertEqual(load_settings(self.ENV).admin_scope, "admin-api kc-admin-api")

    def test_webhook_secret_must_be_long_enough(self) -> None:
        # The event listener fork also refuses a secret shorter than 16 characters.
        with self.assertRaises(ConfigError) as caught:
            load_settings({**self.ENV, "IDENTITY_SYNC_WEBHOOK_SECRET": "kisa-anahtar"})
        self.assertIn("IDENTITY_SYNC_WEBHOOK_SECRET", str(caught.exception))
        self.assertNotIn("kisa-anahtar", str(caught.exception))

    def test_digest_key_is_required_and_hidden(self) -> None:
        missing = {k: v for k, v in self.ENV.items() if k != "IDENTITY_SYNC_DIGEST_KEY"}
        with self.assertRaises(ConfigError) as caught:
            load_settings(missing)
        self.assertIn("IDENTITY_SYNC_DIGEST_KEY", str(caught.exception))
        with self.assertRaises(ConfigError):
            load_settings({**self.ENV, "IDENTITY_SYNC_DIGEST_KEY": "kisa"})
        self.assertNotIn("test-digest-key", repr(load_settings(self.ENV)))

    def test_client_cannot_be_in_both_lists(self) -> None:
        with self.assertRaises(ConfigError):
            load_settings({**self.ENV, "IDENTITY_SYNC_PREVIEW_AZP": "ai-agent, approval-service"})

    def test_only_press_may_request_account_deletions_by_default(self) -> None:
        # docs/sozlesmeler.md, section 7: the caller is the press-service client.
        settings = load_settings(self.ENV)
        self.assertEqual(settings.deletion_azp, frozenset({"press-service"}))
        self.assertIn("press-service", settings.known_azp)
        with self.assertRaises(ConfigError):
            load_settings({**self.ENV, "IDENTITY_SYNC_PREVIEW_AZP": "press-service"})

    def test_session_clients_are_their_own_list(self) -> None:
        settings = load_settings(self.ENV)
        self.assertEqual(settings.session_azp, frozenset({"site-kiraci1"}))
        self.assertIn("site-kiraci1", settings.known_azp)
        with self.assertRaises(ConfigError):
            load_settings({**self.ENV, "IDENTITY_SYNC_PREVIEW_AZP": "site-kiraci1"})

    def test_tenant_site_client_may_execute_and_revoke_sessions(self) -> None:
        # docs/sozlesmeler.md, section 7: the approval is given on the tenant site, so the execute
        # list holds the tenant service clients. It carries the same clients as the session list.
        both = {**self.ENV, "IDENTITY_SYNC_EXECUTE_AZP": "site-kiraci1", "IDENTITY_SYNC_SESSION_AZP": "site-kiraci1"}

        settings = load_settings(both)

        self.assertEqual((settings.execute_azp, settings.session_azp), (frozenset({"site-kiraci1"}),) * 2)

    def test_every_other_pair_of_lists_stays_separate(self) -> None:
        pairs = (
            ("EXECUTE", "PREVIEW"),
            ("SESSION", "PREVIEW"),
            ("DELETION", "PREVIEW"),
            ("DELETION", "EXECUTE"),
            ("DELETION", "SESSION"),
        )
        for first, second in pairs:
            with self.subTest(pair=(first, second)), self.assertRaises(ConfigError):
                env = {key: value for key, value in self.ENV.items() if not key.endswith("_AZP")}
                load_settings({**env, f"IDENTITY_SYNC_{first}_AZP": "same", f"IDENTITY_SYNC_{second}_AZP": "same"})

    def test_client_lists_default_to_empty(self) -> None:
        env = {k: v for k, v in self.ENV.items() if not k.endswith("_AZP")}
        settings = load_settings(env)

        self.assertEqual((settings.execute_azp, settings.preview_azp), (frozenset(), frozenset()))

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


class LoggingTest(unittest.TestCase):
    def test_serve_logging_keeps_info_records(self) -> None:
        # İşlem günlüğü INFO düzeyindedir. Ayar yapılmazsa Python bu kayıtları atar.
        import logging

        stream = io.StringIO()
        logger = logging.getLogger("identity_sync")
        before = (logger.level, list(logger.handlers), logger.propagate)
        self.addCleanup(lambda: (logger.setLevel(before[0]), setattr(logger, "handlers", before[1]), setattr(logger, "propagate", before[2])))

        cli.configure_logging(stream)
        logger.info("execute operation=%s", "deneme")

        self.assertIn("execute operation=deneme", stream.getvalue())
        self.assertIn("INFO", stream.getvalue())


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.keycloak, self.press, self.tenant = FakeKeycloak(), FakePress(), FakeTenant()
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
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(args), env=self.env)
        # A refused command prints its reason to stderr and nothing to stdout.
        return code, json.loads(out.getvalue() or "null")

    def queue_failed_event(self, event_id: str = "e-1") -> None:
        from identity_sync.app import build_app
        from identity_sync.events import Event

        self.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        app = build_app(load_settings(self.env), sleep=lambda _s: None)
        app.processor.handle(Event(id=event_id, kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=SUBJECT))
        app.close()
        self.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)

    def test_serve_reports_an_address_the_token_library_refuses(self) -> None:
        # Found by starting the real container: the library takes plain http only for localhost.
        # The service must say so and stop, not die with a traceback.
        import sys
        import types

        library = types.ModuleType("oidc_verify")

        def refuse(url: str, **_options: object) -> None:
            raise ValueError("jwks_url must use https; plain http is allowed only for localhost and loopback")

        library.JwksCache = refuse
        previous = sys.modules.get("oidc_verify")
        sys.modules["oidc_verify"] = library
        self.addCleanup(lambda: sys.modules.pop("oidc_verify") if previous is None else sys.modules.update(oidc_verify=previous))
        errors = io.StringIO()

        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["serve"], env=self.env)

        self.assertEqual(code, 2)
        self.assertIn("configuration error: token verification cannot start", errors.getvalue())
        self.assertIn("IDENTITY_SYNC_KEYCLOAK_INTERNAL_URL", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

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

    def replay(self, *extra: str, approval: str = "onay-r1") -> tuple[int, dict]:
        """Preview, then execute with the digest of that preview, like a human would."""
        _code, preview = self.run_cli("replay-dead-letters", *extra)
        return self.run_cli(
            "replay-dead-letters", "--execute", "--preview-digest", preview["preview_digest"], "--approval-id", approval, *extra
        )

    def test_replay_empties_queue(self) -> None:
        self.queue_failed_event()

        code, body = self.replay()

        self.assertEqual((code, body["results"][0]["status"]), (0, "processed"))
        self.assertEqual(self.run_cli("dead-letters")[1], {"dead_letters": []})

    def test_replay_only_previews_by_default(self) -> None:
        # frappe-python-standartlari.md, V-10: work that cannot be undone is tried without writing first.
        self.queue_failed_event()
        before = len(self.writes())

        code, body = self.run_cli("replay-dead-letters")

        self.assertEqual((code, body["results"][0]["status"]), (0, "preview"))
        self.assertRegex(body["preview_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(self.writes()), before)

    def test_replay_execute_needs_the_preview_digest_and_an_approval(self) -> None:
        self.queue_failed_event()
        before = len(self.writes())
        for arguments in (
            ("--execute",),
            ("--execute", "--preview-digest", "0" * 64),
            ("--execute", "--approval-id", "onay-r2"),
            ("--execute", "--dry-run", "--preview-digest", "0" * 64, "--approval-id", "onay-r2"),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as stopped, contextlib.redirect_stderr(io.StringIO()):
                    cli.main(["replay-dead-letters", *arguments], env=self.env)
                self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(len(self.writes()), before)

    def test_replay_with_a_stale_digest_writes_nothing(self) -> None:
        self.queue_failed_event()
        before = len(self.writes())

        code, _body = self.run_cli("replay-dead-letters", "--execute", "--preview-digest", "0" * 64, "--approval-id", "onay-r3")

        self.assertEqual(code, 2)
        self.assertEqual(len(self.writes()), before)

    def test_replay_approval_works_once(self) -> None:
        self.queue_failed_event()
        self.assertEqual(self.replay(approval="onay-r4")[0], 0)
        self.queue_failed_event("e-2")

        code, _body = self.replay(approval="onay-r4")

        self.assertEqual(code, 2)
        self.assertEqual(len(self.run_cli("dead-letters")[1]["dead_letters"]), 1)

    def test_replay_leaves_unknown_events_unless_asked(self) -> None:
        self.tenant.on("POST", fakes.TENANT_PROVISION, (202, {"message": {"status": "queued"}}))
        from identity_sync.app import build_app
        from identity_sync.events import Event

        app = build_app(load_settings(self.env), sleep=lambda _s: None)
        app.processor.handle(Event(id="e-1", kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=SUBJECT))
        app.close()
        self.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)

        code, body = self.replay(approval="onay-u1")
        self.assertEqual((code, body["results"][0]["status"]), (1, "unknown"))

        code, body = self.replay("--include-unknown", approval="onay-u2")
        self.assertEqual((code, body["results"][0]["status"]), (0, "processed"))

    def test_replay_fails_when_event_still_fails(self) -> None:
        self.queue_failed_event()
        self.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))

        code, _body = self.replay()

        self.assertEqual(code, 1)

    def drift(self) -> None:
        # The tenant lost the user's link. Press still has the membership.
        self.keycloak.serve_directory()
        issuer = f"{self.keycloak.url}/realms/platform"
        self.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID)

    def writes(self) -> list[fakes.Recorded]:
        keycloak_writes = [r for r in self.keycloak.requests if r.method != "GET" and "/admin/" in r.path]
        return self.press.writes() + self.tenant.writes() + keycloak_writes

    def test_reconcile_is_a_dry_run_by_default(self) -> None:
        self.drift()

        for arguments in (("reconcile",), ("reconcile", "--dry-run")):
            with self.subTest(arguments=arguments):
                code, body = self.run_cli(*arguments)
                self.assertEqual(code, 1)
                self.assertEqual(body["differences"], [{"target": "kiraci1", "subject": SUBJECT, "kind": "missing"}])
                self.assertEqual(
                    [p["operation"] for p in body["previews"]], ["tenant.change_email", "tenant.provision"]
                )
        self.assertEqual(self.writes(), [])

    def test_reconcile_without_difference_exits_zero(self) -> None:
        self.keycloak.remove_user(SUBJECT)
        self.keycloak.users.clear()
        self.keycloak.serve_directory()

        code, body = self.run_cli("reconcile")

        self.assertEqual((code, body["count"], body["differences"]), (0, 0, []))

    def test_reconcile_execute_needs_digest_and_approval(self) -> None:
        self.drift()
        err = io.StringIO()
        for arguments in (("--execute",), ("--execute", "--preview-digest", "a" * 64), ("--execute", "--approval-id", "x")):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    cli.main(["reconcile", *arguments], env=self.env)
                self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.writes(), [])

    def test_reconcile_execute_runs_the_previewed_repair_once(self) -> None:
        self.drift()
        _code, preview = self.run_cli("reconcile")
        arguments = ("reconcile", "--execute", "--preview-digest", preview["preview_digest"], "--approval-id", "onay-k1")

        code, body = self.run_cli(*arguments)

        self.assertEqual(code, 0)
        self.assertEqual([r["status"] for r in body["results"]], ["done", "done"])
        self.assertEqual(self.run_cli("reconcile")[0], 0)
        # The approval is spent.
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(list(arguments), env=self.env), 2)
        self.assertIn("approval", err.getvalue())

    def test_reconcile_execute_refuses_a_stale_digest(self) -> None:
        self.drift()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(
                ["reconcile", "--execute", "--preview-digest", "0" * 64, "--approval-id", "onay-k2"], env=self.env
            )

        self.assertEqual(code, 2)
        self.assertIn("preview", err.getvalue())
        self.assertEqual(self.writes(), [])

    def test_operations_lists_and_resolves_unfinished_work(self) -> None:
        from identity_sync.app import build_app

        app = build_app(load_settings(self.env), sleep=lambda _s: None)
        app.store.operation_begin("onay-9", "invite_user", ORG_ID, ["keycloak.create_user"])
        app.store.operation_step("onay-9", "keycloak.create_user", "writing")
        app.close()

        code, body = self.run_cli("operations")
        self.assertEqual((code, body["operations"][0]["operation_id"], body["operations"][0]["state"]), (1, "onay-9", "unknown"))

        code, body = self.run_cli("resolve-operation", "onay-9", "--resolution", "abandoned")
        self.assertEqual((code, body), (0, {"operation_id": "onay-9", "state": "resolved", "resolution": "abandoned"}))
        self.assertEqual(self.run_cli("operations"), (0, {"operations": []}))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["resolve-operation", "onay-9", "--resolution", "abandoned"], env=self.env), 2)

    def test_missing_settings_exit_with_two(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["reconcile"], env={})
        self.assertEqual(code, 2)
        self.assertIn("IDENTITY_SYNC_CLIENT_SECRET", err.getvalue())


if __name__ == "__main__":
    unittest.main()
