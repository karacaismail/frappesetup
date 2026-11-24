"""Check how the shared stack delivers the Press site configuration."""

import json
import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


STACK = Path(__file__).resolve().parents[1] / "stack"


class StackPressTest(unittest.TestCase):
    def test_press_config_uses_stack_origins_and_passes_secrets_through_stdin(self):
        configure = runpy.run_path(str(STACK))["configure_press"]
        environment = {
            "ATONOTA_PRESS_URL": "http://press.localhost:43823",
            "KC_PUBLIC_URL": "http://identity.localhost:43820",
            "ATONOTA_PRESS_SECRET": "synthetic-client-secret",
            "ATONOTA_PRESS_SERVICE_SECRET": "synthetic-service-secret",
        }

        with patch.dict(configure.__globals__, {"run": Mock()}) as scope:
            configure(["compose"], environment)
            call = scope["run"].call_args
        command, env = call.args
        self.assertIs(env, environment)
        self.assertEqual(command[:8], [
            "compose", "exec", "-T", "--workdir", "/home/frappe/benches/frappe-bench",
            "web", "env/bin/python", "-c",
        ])
        self.assertNotIn(environment["ATONOTA_PRESS_SECRET"], " ".join(command))
        self.assertNotIn(environment["ATONOTA_PRESS_SERVICE_SECRET"], " ".join(command))
        config = json.loads(call.kwargs["input"])
        self.assertEqual(config["host_name"], environment["ATONOTA_PRESS_URL"])
        self.assertEqual(config["keycloak_public_url"], environment["KC_PUBLIC_URL"])
        self.assertEqual(config["keycloak_internal_url"], environment["KC_PUBLIC_URL"])
        self.assertEqual(config["keycloak_realm"], "platform")
        self.assertEqual(config["keycloak_client_id"], "press")
        self.assertEqual(config["keycloak_client_secret"], environment["ATONOTA_PRESS_SECRET"])
        self.assertEqual(config["press_service_client_secret"], environment["ATONOTA_PRESS_SERVICE_SECRET"])
        self.assertEqual(config["identity_sync_url"], "http://identity-sync.localhost:6115")

    def test_existing_sync_user_must_be_enabled_website_user(self):
        frappe = Mock()
        script = STACK.parent / "preview" / "configure-stack-press.py"
        with patch.dict("sys.modules", {"frappe": frappe}):
            ensure_user = runpy.run_path(str(script))["ensure_sync_user"]
        for record in ((0, "Website User"), (1, "System User")):
            with self.subTest(record=record):
                frappe.db.get_value.return_value = record
                with self.assertRaisesRegex(ValueError, "enabled Website User"):
                    ensure_user("identity-sync@example.test")
        frappe.db.get_value.return_value = (1, "Website User")
        ensure_user("identity-sync@example.test")
        frappe.get_doc.assert_not_called()
