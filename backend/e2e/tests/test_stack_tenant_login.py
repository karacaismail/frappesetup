"""Check the development tenant's browser origin and exact realm redirects."""

import json
import runpy
import unittest
from pathlib import Path
from secrets import token_hex
from unittest.mock import Mock, patch


STACK = runpy.run_path(str(Path(__file__).resolve().parents[1] / "stack"))


class StackTenantLoginTest(unittest.TestCase):
    def test_up_configures_login_after_bootstrap(self):
        up = STACK["up"]
        run = Mock()
        run.return_value.stdout = "platform-id"
        configure = Mock(side_effect=RuntimeError("stop after configuring tenant login"))
        environment = {"ATONOTA_SITE_TENANT1_SECRET": token_hex(16)}
        dependencies = {
            name: Mock()
            for name in ("require_press_settings", "require_tenant_settings", "require_realm_sync_settings",
                         "check_resources", "config", "ensure_images", "sync_realm")
        }
        with patch.dict(up.__globals__, dependencies | {"run": run, "configure_tenant_login": configure}):
            with self.assertRaisesRegex(RuntimeError, "stop after configuring tenant login"):
                up(["docker"], ["compose"], environment)
        self.assertIn("/workspace/dev/bootstrap.py", run.call_args.args[0])
        configure.assert_called_once_with(["compose"], environment)

    def test_vite_redirect_is_explicit_and_keeps_the_tenant_backchannel(self):
        environment = {
            "ATONOTA_SITE_TENANT1_URL": "http://tenant1.localhost:7401",
            "ATONOTA_SITE_TENANT1_SECRET": token_hex(16),
            "KC_PUBLIC_URL": "http://identity.localhost:7400",
        }
        for vite, origin in (("0", environment["ATONOTA_SITE_TENANT1_URL"]), ("1", "http://localhost:5180")):
            with self.subTest(vite=vite):
                environment["FS_STACK_VITE"] = vite
                realm = json.loads(STACK["REALM_FILE"].read_text())
                tenant = next(client for client in realm["clients"] if client["clientId"] == "site-tenant1")
                original_uris = tenant["redirectUris"].copy()
                backchannel = tenant["attributes"]["backchannel.logout.url"]
                logout = tenant["attributes"]["post.logout.redirect.uris"]

                STACK["stack_realm"](realm, environment)
                settings = STACK["tenant_login_settings"](environment)

                if vite == "1":
                    self.assertEqual(settings["host_name"], origin)
                else:
                    self.assertNotIn("host_name", settings)
                self.assertEqual(settings["platform_panel_url"], origin + "/panel")
                self.assertEqual(tenant["attributes"]["backchannel.logout.url"], backchannel)
                expected = original_uris + ([origin + STACK["TENANT_CALLBACK"]] if vite == "1" else [])
                self.assertEqual(tenant["redirectUris"], expected)
                recovery = "/api/method/platform_core.api.auth.start_login?switch_account=1"
                self.assertIn(environment["ATONOTA_SITE_TENANT1_URL"] + recovery,
                              logout.replace("${ATONOTA_SITE_TENANT1_URL}", environment["ATONOTA_SITE_TENANT1_URL"]))
                expected_logout = "##".join((logout, origin + "/panel", origin + recovery)) if vite == "1" else logout
                self.assertEqual(tenant["attributes"]["post.logout.redirect.uris"], expected_logout)
