"""T-11: stack up applies the realm file to a kept Keycloak database before the services use it."""

import json
import runpy
import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

STACK = Path(__file__).resolve().parents[1] / "stack"
BACKEND = STACK.parents[1]


def environment():
    realm = (BACKEND / "identity/keycloak/realm/platform-realm.json").read_text()
    script = runpy.run_path(str(BACKEND / "identity/keycloak/bin/sync-dev-realm.py"))
    names = set(script["PLACEHOLDER"].findall(realm))
    values = {name: f"synthetic-{name.lower()}" for name, _ in names if name.isupper()}
    values.update(
        {
            "KC_PUBLIC_URL": "http://identity.localhost:43820",
            # Values are made at run time so no credential-like literal sits in the source.
            "KC_BOOTSTRAP_ADMIN_USERNAME": secrets.token_hex(8),
            "KC_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(16),
            "UNRELATED_SECRET": secrets.token_urlsafe(16),
        }
    )
    return values


class StackRealmSyncTest(unittest.TestCase):
    def test_realm_sync_runs_in_the_stack_network_and_passes_secrets_through_stdin(self):
        sync = runpy.run_path(str(STACK))["sync_realm"]
        values = environment()
        with patch.dict(sync.__globals__, {"run": Mock()}) as scope:
            sync(["compose"], values)
            call = scope["run"].call_args
        command, env = call.args
        self.assertIs(env, values)
        self.assertEqual(
            command[:9], ["compose", "run", "--rm", "--no-deps", "-T", "identity-sync", "python", "-I", "-c"]
        )
        self.assertEqual(command[9], (BACKEND / "identity/keycloak/bin/sync-dev-realm.py").read_text())
        self.assertEqual(command[10:], ["--stdin"])
        joined = " ".join(command)
        for secret in ("KC_BOOTSTRAP_ADMIN_PASSWORD", "ATONOTA_SITE_TENANT1_SECRET", "ATONOTA_PRESS_SECRET"):
            self.assertNotIn(values[secret], joined)
        payload = json.loads(call.kwargs["input"])
        self.assertEqual(payload["keycloak_url"], values["KC_PUBLIC_URL"])
        self.assertEqual(payload["admin_username"], values["KC_BOOTSTRAP_ADMIN_USERNAME"])
        self.assertEqual(payload["admin_password"], values["KC_BOOTSTRAP_ADMIN_PASSWORD"])
        self.assertEqual(payload["realm"]["realm"], "platform")
        redirect = "ATONOTA_MOBILE_REDIRECT_URI"
        self.assertEqual(payload["values"][redirect], values[redirect])
        # Only the names the realm file uses travel; other secrets stay out.
        self.assertNotIn("UNRELATED_SECRET", payload["values"])

    def test_up_syncs_the_realm_after_keycloak_is_ready_and_before_identity_sync(self):
        namespace = runpy.run_path(str(STACK))
        up = namespace["up"]
        order = []

        def run(command, env, **kwargs):
            order.append(" ".join(command))
            return SimpleNamespace(stdout="realm-id", returncode=0)

        replacements = {
            "run": run,
            "sync_realm": lambda compose, env: order.append("sync_realm"),
            "require_press_settings": Mock(),
            "check_resources": Mock(),
            "config": Mock(return_value={}),
            "ensure_images": Mock(),
            "configure_press": Mock(),
            "check": Mock(),
            "resources": Mock(),
            "container_ids": Mock(return_value=[]),
        }
        with patch.dict(up.__globals__, replacements):
            up(["engine"], ["compose"], dict(environment(), PANE_PORT="43820"))
        keycloak_up = next(
            i for i, line in enumerate(order) if line.startswith("compose up") and " keycloak" in line
        )
        identity_sync_up = next(i for i, line in enumerate(order) if line.endswith("--wait identity-sync"))
        self.assertLess(keycloak_up, order.index("sync_realm"))
        self.assertLess(order.index("sync_realm"), identity_sync_up)


if __name__ == "__main__":
    unittest.main()
