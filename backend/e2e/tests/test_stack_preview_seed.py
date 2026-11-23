"""MVP test 3, T-16 and T-17: the stack seeds the preview fixtures and names a foreign container.

T-16: `stack seed-preview` prepares the API and browser test data on a running stack with the
preview fixture helpers. T-17: a container started with `docker run` from the stack's tenant image
inherits the image's Compose project label. The owner check must name that container.
"""

import json
import os
import runpy
import secrets
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

STACK = Path(__file__).resolve().parents[1] / "stack"
PREVIEW = STACK.parent / "preview"
PORT = "43820"


def stack_environment():
    return {
        "PANE_PORT": PORT,
        "FS_COLIMA_PROFILE": "factory",
        "KC_PORT": PORT,
        "KC_PUBLIC_URL": f"http://identity.localhost:{PORT}",
        "ATONOTA_SITE_TENANT1_URL": f"http://tenant1.localhost:{int(PORT) + 1}",
        "IDENTITY_BRAND_NAME": "AtonotA Login",
        "IDENTITY_SYNC_EVENTS_URL": "http://identity-sync.localhost:6115/v1/events",
        "ATONOTA_SITE_TENANT1_SECRET": secrets.token_urlsafe(16),
        "ATONOTA_SITE_TENANT1_SERVICE_SECRET": secrets.token_urlsafe(16),
        "KC_BOOTSTRAP_ADMIN_USERNAME": secrets.token_hex(8),
        "KC_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(16),
    }


def completed(command, stdout=""):
    return SimpleNamespace(args=command, returncode=0, stdout=stdout)


class OwnerMessageTest(unittest.TestCase):
    def owner_error(self, container):
        namespace = runpy.run_path(str(STACK))
        env_path = str(STACK.parents[1] / "e2e/.env")
        outputs = iter(["a" * 12 + "\n", json.dumps([container])])

        def docker(command, environment, **kwargs):
            return completed(command, next(outputs))

        with patch.dict(namespace["assert_owner"].__globals__, {"run": docker}):
            with self.assertRaises(ValueError) as caught:
                namespace["assert_owner"](["docker"], ["compose", "--env-file", env_path], {"PANE_PORT": PORT})
        return str(caught.exception)

    def test_names_a_container_that_inherited_the_image_label(self):
        message = self.owner_error({
            "Name": "/mvp3-e2e-provider",
            "Config": {"Labels": {"com.docker.compose.project": "fs-e2e-43820-x", "com.docker.compose.service": "tenant-web"}},
        })
        self.assertIn("mvp3-e2e-provider", message)
        self.assertIn("image", message)
        self.assertIn("com.docker.compose.project=", message)
        self.assertNotIn("belongs to another worktree", message)

    def test_names_the_container_and_folder_of_another_worktree(self):
        message = self.owner_error({
            "Name": "/fs-e2e-43820-x-tenant-web-1",
            "Config": {"Labels": {"com.docker.compose.project.working_dir": "/another/worktree/backend/dev"}},
        })
        self.assertIn("another worktree", message)
        self.assertIn("fs-e2e-43820-x-tenant-web-1", message)
        self.assertIn("/another/worktree/backend/dev", message)


class SeedPreviewTest(unittest.TestCase):
    def setUp(self):
        self.namespace = runpy.run_path(str(STACK))
        self.environment = stack_environment()
        self.project = self.namespace["project_name"](self.environment)
        self.calls = []

    def docker(self, command, environment, **kwargs):
        self.calls.append((command, kwargs))
        if command[1] == "ps":
            return completed(command, "")
        if command[1] == "inspect" and "{{.Config.Image}}" in command:
            return completed(command, "fs-tenant-dev:synthetic\n")
        if command[1] == "inspect":
            return completed(command, "10.89.0.7\n")
        if command[1] == "run":
            return completed(command, "b" * 64 + "\n")
        if "exec" in command:
            return completed(command, "Frappe output\n" + json.dumps({"E2E_DOCTYPE": "Preview Access Request"}))
        self.fail(f"Unexpected command: {command}")

    def fixtures(self):
        lifecycle = {"chromium_delete": {
            "email": "d@example.test", "subject": "s-1", "password": secrets.token_urlsafe(16),
        }}
        self.keycloak_password = secrets.token_urlsafe(16)
        return SimpleNamespace(
            LOGIN_EMAIL="e2e-user@example.test",
            keycloak_request=Mock(return_value=[]),
            admin_access_token=Mock(return_value="synthetic-admin-token"),
            seed_identities=Mock(return_value=("synthetic", {"E2E_MOBILE_AUDIENCE": "site-tenant1"}, lifecycle, {})),
            lifecycle_identities=Mock(return_value='{"chromium_delete": {"email": "d@example.test"}}'),
            account_fixtures=Mock(side_effect=lambda fixture, lifecycle, browser, password, sync: {
                **fixture, **browser, "E2E_KEYCLOAK_PASSWORD": self.keycloak_password,
            }),
        )

    def seed(self, fixtures):
        function = self.namespace["seed_preview"]
        with (
            patch.dict(function.__globals__, {"run": self.docker, "preview_fixtures": lambda: fixtures}),
            patch.dict(os.environ, {}, clear=False),
        ):
            result = function(["docker"], ["compose"], self.environment)
            seen = {key: os.environ.get(key) for key in (
                "E2E_KEYCLOAK_CLIENT_SECRET", "E2E_KEYCLOAK_ADMIN_USER", "E2E_FULL_BROWSER_FIXTURES",
            )}
        return result, seen

    def test_provider_drops_the_image_compose_labels(self):
        self.seed(self.fixtures())
        command = next(command for command, _ in self.calls if command[1] == "run")
        labels = [command[index + 1] for index, value in enumerate(command) if value == "--label"]
        self.assertIn("com.docker.compose.project=", labels)
        self.assertIn("com.docker.compose.service=", labels)
        self.assertIn(f"io.frappesetup.stack-extra={self.project}", labels)
        self.assertIn(f"{self.project}-provider", command)
        self.assertIn(f"{self.project}_default", command)
        self.assertIn("fs-tenant-dev:synthetic", command)

    def test_seeds_the_tenant_with_the_preview_helpers_and_keeps_secrets_off_the_command_line(self):
        fixtures = self.fixtures()
        result, seen = self.seed(fixtures)
        fixtures.seed_identities.assert_called_once_with(int(PORT))
        self.assertEqual(seen["E2E_KEYCLOAK_CLIENT_SECRET"], self.environment["ATONOTA_SITE_TENANT1_SECRET"])
        self.assertEqual(seen["E2E_KEYCLOAK_ADMIN_USER"], self.environment["KC_BOOTSTRAP_ADMIN_USERNAME"])
        self.assertEqual(seen["E2E_FULL_BROWSER_FIXTURES"], "1")
        command, kwargs = next((c, k) for c, k in self.calls if "exec" in c)
        self.assertEqual(command[:6], ["compose", "exec", "-T", "tenant-web", "env/bin/python", "-c"])
        self.assertEqual(command[6], (PREVIEW / "site-seed.py").read_text())
        self.assertEqual(command[7:], ["stack-tenant"])
        settings = json.loads(kwargs["input"])
        self.assertEqual(settings["E2E_PROVIDER_IP"], "10.89.0.7")
        self.assertEqual(settings["E2E_PREVIEW_SYNC_ORIGIN"], "http://identity-sync.localhost:6115")
        joined = " ".join(part for call, _ in self.calls for part in call)
        for key in ("ATONOTA_SITE_TENANT1_SECRET", "KC_BOOTSTRAP_ADMIN_PASSWORD"):
            self.assertNotIn(self.environment[key], joined)
        self.assertEqual(result["E2E_DOCTYPE"], "Preview Access Request")
        self.assertEqual(result["E2E_MOBILE_AUDIENCE"], "site-tenant1")
        self.assertEqual(result["E2E_KEYCLOAK_PASSWORD"], self.keycloak_password)

    def test_refuses_a_stack_that_already_holds_the_fixtures(self):
        fixtures = self.fixtures()
        fixtures.keycloak_request.return_value = [{"id": "existing"}]
        with self.assertRaisesRegex(ValueError, "already"):
            self.seed(fixtures)
        fixtures.seed_identities.assert_not_called()

    def test_command_line_offers_seed_preview(self):
        source = STACK.read_text()
        self.assertIn('"seed-preview"', source)
        self.assertIn('elif args.action == "seed-preview":', source)

    def test_down_removes_only_this_stacks_provider(self):
        stop = self.namespace["stop_provider"]
        calls = []

        def docker(command, environment, **kwargs):
            calls.append(command)
            return completed(command, "c" * 64 + "\n" if command[1] == "ps" else "")

        with patch.dict(stop.__globals__, {"run": docker}):
            stop(["docker"], self.environment)
        self.assertIn(f"label=io.frappesetup.stack-extra={self.project}", calls[0])
        self.assertEqual(calls[1], ["docker", "rm", "-f", "c" * 64])


class DownTest(unittest.TestCase):
    def test_down_removes_the_provider_before_compose_down(self):
        namespace = runpy.run_path(str(STACK))
        main = namespace["main"]
        environment = stack_environment()
        calls = []

        def docker(command, env, **kwargs):
            calls.append(command)
            return completed(command, "d" * 64 + "\n" if command[1] == "ps" else "")

        with (
            patch.dict(main.__globals__, {
                "run": docker,
                "setup": lambda: (environment, ["docker"], ["compose"]),
                "assert_owner": lambda *args, **kwargs: None,
            }),
            patch.object(sys, "argv", ["stack", "down"]),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual([call[:3] for call in calls], [
            ["docker", "ps", "-aq"], ["docker", "rm", "-f"], ["compose", "down"],
        ])


class SiteSeedStackModeTest(unittest.TestCase):
    def test_stack_mode_keeps_stack_keycloak_settings_and_points_the_gateway_at_the_provider(self):
        source = PREVIEW / "site-seed.py"
        frappe = Mock()
        frappe.init.side_effect = StopIteration
        kept = secrets.token_urlsafe(16)
        existing = {"keycloak_client_secret": kept, "developer_mode": True}
        settings = {
            "PANE_PORT": PORT,
            "E2E_PROVIDER_IP": "10.89.0.7",
            "E2E_PREVIEW_SYNC_ORIGIN": "http://identity-sync.localhost:6115",
            "E2E_PREVIEW_LOGIN_EMAIL": "e2e-user@example.test",
            "E2E_LIFECYCLE_IDENTITIES": "{}",
        }
        with patch.dict(sys.modules, {"frappe": frappe}):
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", ["-c", "stack-tenant"]),
                patch.object(sys, "stdin", Mock(read=Mock(return_value=json.dumps(settings)))),
                patch.object(os, "chdir"),
                patch.object(Path, "read_text", return_value=json.dumps(existing)),
                patch.object(Path, "write_text") as write,
                patch.object(Path, "chmod"),
                patch.object(Path, "replace") as replace,
                self.assertRaises(StopIteration),
            ):
                runpy.run_path(str(source), run_name="__main__")
        self.assertEqual(replace.call_args.args, (Path("sites/tenant1.localhost/site_config.json"),))
        config = json.loads(write.call_args.args[0])
        self.assertEqual(config["keycloak_client_secret"], kept)
        self.assertNotIn("extra_config", config)
        self.assertEqual(config["mobile_identity_sync_url"], "http://identity-sync.localhost:6115")
        self.assertEqual(config["mobile_allow_development_http"], 1)
        self.assertEqual(config["allow_cors"], [f"http://127.0.0.1:{int(PORT) + 8}"])
        self.assertEqual(
            config["model_gateway_endpoints"],
            {
                f"http://e2e-provider:{int(PORT) + 7}/{part}": {"kind": "local", "addresses": ["10.89.0.7"]}
                for part in ("limited", "fallback")
            },
        )


class PreviewHelpersTest(unittest.TestCase):
    def test_preview_and_stack_share_the_account_mapping(self):
        source = (PREVIEW / "fixtures.py").read_text()
        for name in ("def seed_identities(", "def lifecycle_identities(", "def account_fixtures("):
            self.assertIn(name, source)
        main = source[source.index("def main():"):]
        self.assertIn("seed_identities(port)", main)
        self.assertIn("account_fixtures(", main)


if __name__ == "__main__":
    unittest.main()
