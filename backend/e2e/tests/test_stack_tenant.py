"""MVP test 2, row 5e: the shared stack prepares the tenant for the Press deletion chain.

The stack installs HRMS TR on the tenant that Press is bound to, writes the tenant's Keycloak
settings, and seeds one synthetic deletion fixture. Secrets travel on stdin, never on a command line.
"""

import json
import runpy
import secrets
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

STACK = Path(__file__).resolve().parents[1] / "stack"
PREVIEW = STACK.parent / "preview"
PORT = "43820"
PRODUCT_NAME = runpy.run_path(str(STACK.parents[1] / "deploy/brand.py"))["load_brand"]()["PRODUCT_NAME"]


def stack_environment():
    return {
        "PANE_PORT": PORT,
        "KC_PUBLIC_URL": f"http://identity.localhost:{PORT}",
        "ATONOTA_SITE_TENANT1_URL": f"http://tenant1.localhost:{int(PORT) + 1}",
        "ATONOTA_PRESS_URL": f"http://press.localhost:{int(PORT) + 3}",
        "ATONOTA_SITE_TENANT1_SECRET": secrets.token_urlsafe(16),
        "ATONOTA_SITE_TENANT1_SERVICE_SECRET": secrets.token_urlsafe(16),
        "ATONOTA_PRESS_SECRET": secrets.token_urlsafe(16),
        "ATONOTA_PRESS_SERVICE_SECRET": secrets.token_urlsafe(16),
        "IDENTITY_BRAND_NAME": PRODUCT_NAME,
        "KC_BOOTSTRAP_ADMIN_USERNAME": secrets.token_hex(8),
        "KC_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(16),
        "ATONOTA_IDENTITY_SYNC_SECRET": secrets.token_urlsafe(16),
    }


class StackTenantTest(unittest.TestCase):
    def test_tenant_config_uses_stack_origins_and_passes_secrets_through_stdin(self):
        configure = runpy.run_path(str(STACK))["configure_tenant"]
        environment = stack_environment()
        with patch.dict(configure.__globals__, {"run": Mock()}) as scope:
            configure(["compose"], environment)
            call = scope["run"].call_args
        command, env = call.args
        self.assertIs(env, environment)
        self.assertEqual(command[:6], ["compose", "exec", "-T", "tenant-web", "env/bin/python", "-c"])
        self.assertEqual(command[6], (PREVIEW / "configure-stack-tenant.py").read_text())
        joined = " ".join(command)
        for key in ("ATONOTA_SITE_TENANT1_SECRET", "ATONOTA_SITE_TENANT1_SERVICE_SECRET"):
            self.assertNotIn(environment[key], joined)
        config = json.loads(call.kwargs["input"])
        self.assertEqual(config["keycloak_public_url"], environment["KC_PUBLIC_URL"])
        self.assertEqual(config["keycloak_internal_url"], environment["KC_PUBLIC_URL"])
        self.assertEqual(config["keycloak_realm"], "platform")
        self.assertEqual(config["keycloak_client_id"], "site-tenant1")
        self.assertEqual(config["keycloak_client_secret"], environment["ATONOTA_SITE_TENANT1_SECRET"])
        self.assertEqual(config["keycloak_service_client_id"], "site-tenant1-service")
        self.assertEqual(
            config["keycloak_service_client_secret"], environment["ATONOTA_SITE_TENANT1_SERVICE_SECRET"]
        )
        self.assertEqual(config["identity_brand_name"], PRODUCT_NAME)
        self.assertEqual(config["platform_panel_url"], environment["ATONOTA_SITE_TENANT1_URL"] + "/panel")
        # The deletion key is made inside the site, so it never leaves the sites volume.
        self.assertNotIn("kimlik_deletion_hmac_key", config)

    def test_tenant_config_script_keeps_an_existing_deletion_key(self):
        source = PREVIEW / "configure-stack-tenant.py"
        namespace = runpy.run_path(str(source))
        existing = {"db_name": "kept", "kimlik_deletion_hmac_key": "kept-key", "keycloak_client_id": "old"}
        merged = namespace["merge_settings"](existing, {"keycloak_client_id": "site-tenant1"})
        self.assertEqual(merged["db_name"], "kept")
        self.assertEqual(merged["kimlik_deletion_hmac_key"], "kept-key")
        self.assertEqual(merged["keycloak_client_id"], "site-tenant1")
        fresh = namespace["merge_settings"]({}, {"keycloak_client_id": "site-tenant1"})
        self.assertGreaterEqual(len(fresh["kimlik_deletion_hmac_key"]), 32)
        self.assertNotEqual(fresh["kimlik_deletion_hmac_key"], namespace["merge_settings"]({}, {})["kimlik_deletion_hmac_key"])

    def test_up_installs_hrms_tr_and_configures_the_tenant_before_press(self):
        namespace = runpy.run_path(str(STACK))
        environment = stack_environment()
        commands = []

        def execute(command, env, **kwargs):
            commands.append(list(command))
            stdout = "0123456789ab" if command[-1] == "-q" else "realm-id-1"
            return SimpleNamespace(returncode=0, stdout=stdout)

        with patch.dict(
            namespace["up"].__globals__,
            {
                "check_resources": lambda *args: None,
                "config": lambda *args: {},
                "ensure_images": lambda *args: None,
                "check": lambda *args: None,
                "resources": lambda *args: (0, 0),
                "run": execute,
            },
        ):
            namespace["up"](["docker"], ["compose"], environment)
        bootstrap = next(command for command in commands if "/workspace/dev/bootstrap.py" in command)
        self.assertEqual(bootstrap[bootstrap.index("/workspace/dev/bootstrap.py") + 1], "tenant1.localhost")
        apps = [bootstrap[index + 1] for index, item in enumerate(bootstrap) if item == "--app"]
        self.assertEqual(apps, ["erpnext", "platform_core", "hrms", "hrms_tr"])
        tenant_script = (PREVIEW / "configure-stack-tenant.py").read_text()
        press_script = (PREVIEW / "configure-stack-press.py").read_text()
        tenant_index = next(index for index, command in enumerate(commands) if tenant_script in command)
        press_index = next(index for index, command in enumerate(commands) if press_script in command)
        web_up = next(index for index, command in enumerate(commands) if command[:3] == ["compose", "up", "-d"] and "tenant-web" in command and "web" in command)
        self.assertLess(web_up, tenant_index)
        self.assertLess(tenant_index, press_index)

    def test_up_names_missing_tenant_settings_before_any_docker_call(self):
        namespace = runpy.run_path(str(STACK))
        for missing in ("ATONOTA_SITE_TENANT1_SECRET", "IDENTITY_BRAND_NAME"):
            with self.subTest(missing=missing):
                environment = {key: value for key, value in stack_environment().items() if key != missing}
                with (
                    patch.dict(
                        namespace["up"].__globals__,
                        {
                            "resources": lambda *args: self.fail("Must reject before measuring"),
                            "run": lambda *args, **kwargs: self.fail("Must reject before Docker"),
                        },
                    ),
                    patch("subprocess.run", side_effect=AssertionError("Direct subprocess call")),
                ):
                    with self.assertRaisesRegex(ValueError, missing) as caught:
                        namespace["up"](["docker"], ["compose"], environment)
                for value in environment.values():
                    if value not in (PRODUCT_NAME, PORT):
                        self.assertNotIn(value, str(caught.exception))


class StackDeletionSeedTest(unittest.TestCase):
    def test_seed_runs_keycloak_tenant_and_press_scripts_with_secrets_on_stdin(self):
        namespace = runpy.run_path(str(STACK))
        environment = stack_environment()
        # Made at run time so no credential-like literal sits in the source.
        reader_secret, service_token = secrets.token_urlsafe(16), secrets.token_urlsafe(24)
        outputs = {
            "stack-deletion-keycloak.py": {"subject": "kc-user-1", "reader_client": "e2e-stack-reader", "reader_secret": reader_secret, "service_token": service_token},
            "stack-deletion-tenant.py": {"E2E_DELETE_EMPLOYEE": "HR-EMP-00001", "E2E_DELETE_TENANT_ANONYMOUS_USER": "deleted-user-0123456789abcdef@deleted.invalid", "E2E_DELETE_TENANT_READER_COOKIE": "sid=tenant-sid"},
            "stack-deletion-press.py": {"E2E_DELETE_PRESS_ANONYMOUS_USER": "deleted-0123@invalid.example", "E2E_DELETE_PRESS_READER_COOKIE": "sid=press-sid"},
        }
        scripts = {name: (PREVIEW / name).read_text() for name in outputs}
        calls = []

        def execute(command, env, **kwargs):
            calls.append((list(command), kwargs))
            for name, text in scripts.items():
                if text in command:
                    return SimpleNamespace(returncode=0, stdout=json.dumps(outputs[name]) + "\n")
            self.fail(f"Unexpected command: {command[:4]}")

        with patch.dict(namespace["seed_deletion"].__globals__, {"run": execute}):
            fixture = namespace["seed_deletion"](["compose"], environment)
        self.assertEqual(len(calls), 3)
        keycloak, tenant, press = calls
        self.assertEqual(keycloak[0][:9], ["compose", "run", "--rm", "--no-deps", "-T", "identity-sync", "python", "-I", "-c"])
        keycloak_payload = json.loads(keycloak[1]["input"])
        self.assertEqual(keycloak_payload["keycloak_url"], environment["KC_PUBLIC_URL"])
        self.assertEqual(keycloak_payload["admin_password"], environment["KC_BOOTSTRAP_ADMIN_PASSWORD"])
        self.assertEqual(keycloak_payload["identity_sync_secret"], environment["ATONOTA_IDENTITY_SYNC_SECRET"])
        self.assertRegex(keycloak_payload["email"], r"^e2e-delete-[a-z0-9]+@example\.test$")
        self.assertGreaterEqual(len(keycloak_payload["password"]), 20)
        self.assertEqual(tenant[0][:6], ["compose", "exec", "-T", "tenant-web", "env/bin/python", "-c"])
        self.assertEqual(press[0][:7], ["compose", "exec", "-T", "--workdir", "/home/frappe/benches/frappe-bench", "web", "env/bin/python"])
        for payload in (json.loads(tenant[1]["input"]), json.loads(press[1]["input"])):
            self.assertEqual(payload["issuer"], environment["KC_PUBLIC_URL"] + "/realms/platform")
            self.assertEqual(payload["subject"], "kc-user-1")
            self.assertEqual(payload["email"], keycloak_payload["email"])
        for command, kwargs in calls:
            joined = " ".join(command)
            self.assertNotIn(environment["KC_BOOTSTRAP_ADMIN_PASSWORD"], joined)
            self.assertNotIn(environment["ATONOTA_IDENTITY_SYNC_SECRET"], joined)
            self.assertNotIn(keycloak_payload["password"], joined)
        self.assertEqual(fixture["E2E_PRESS_DELETION"], "1")
        self.assertEqual(fixture["E2E_DELETE_EMAIL"], keycloak_payload["email"])
        self.assertEqual(fixture["E2E_DELETE_PASSWORD"], keycloak_payload["password"])
        self.assertEqual(fixture["E2E_DELETE_SUBJECT"], "kc-user-1")
        self.assertEqual(fixture["E2E_LIFECYCLE_READER_CLIENT"], "e2e-stack-reader")
        self.assertEqual(fixture["E2E_LIFECYCLE_READER_SECRET"], reader_secret)
        self.assertEqual(fixture["E2E_DELETE_SERVICE_TOKEN"], service_token)
        self.assertEqual(fixture["E2E_DELETE_EMPLOYEE"], "HR-EMP-00001")
        self.assertEqual(fixture["E2E_DELETE_PRESS_READER_COOKIE"], "sid=press-sid")
        self.assertTrue(all(key.startswith("E2E_") for key in fixture))

    def test_fixture_file_is_private_and_holds_only_e2e_settings(self):
        namespace = runpy.run_path(str(STACK))
        root = Path(namespace["REPOSITORY"]) / ".pane/scratch"
        root.mkdir(parents=True, exist_ok=True)
        import tempfile

        with tempfile.TemporaryDirectory(dir=root) as folder:
            path = Path(folder) / "deletion.env"
            password = "Aa9! " + secrets.token_urlsafe(8)
            namespace["write_fixture"](path, {"E2E_DELETE_EMAIL": "e2e-delete-a1@example.test", "E2E_DELETE_PASSWORD": password})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), f"E2E_DELETE_EMAIL=e2e-delete-a1@example.test\nE2E_DELETE_PASSWORD={password}\n")
            with self.assertRaises(ValueError):
                namespace["write_fixture"](path, {"PATH": "x"})
            with self.assertRaises(ValueError):
                namespace["write_fixture"](path, {"E2E_X": "line\nbreak"})


if __name__ == "__main__":
    unittest.main()
