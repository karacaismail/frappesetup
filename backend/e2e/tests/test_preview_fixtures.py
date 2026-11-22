"""Check fixture failures without starting Keycloak, Docker, or Frappe."""

import base64
import importlib.util
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from backend.e2e.preview import fixtures


def load_fixtures():
    spec = importlib.util.spec_from_file_location("backend.e2e.preview.fixtures_probe", fixtures.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewFixturesTest(unittest.TestCase):
    def test_resolves_docker_once_for_both_fixture_commands(self):
        with patch("shutil.which", return_value="/tools/docker") as which:
            preview = load_fixtures()
        replies = [
            subprocess.CompletedProcess([], 0, '[200, null, "{}"]'),
            subprocess.CompletedProcess([], 0, "{}"),
        ]
        with patch.dict(os.environ, {"PREVIEW_PROJECT": "fs-e2e-preview-test"}), patch(
            "subprocess.run", side_effect=replies,
        ) as run:
            preview.container_keycloak_request(43820, "GET", "/health", None, {})
            preview.seed_site("fs-e2e-preview-test", "tenant-web", "/bench", {})
        which.assert_called_once_with("docker")
        self.assertEqual([call.args[0][0] for call in run.call_args_list], ["/tools/docker", "/tools/docker"])

    def test_rejects_missing_and_relative_docker_before_running_a_command(self):
        for path in (None, "bin/docker"):
            with self.subTest(path=path), patch("shutil.which", return_value=path):
                preview = load_fixtures()
                with patch("subprocess.run") as run:
                    with self.assertRaisesRegex(RuntimeError, "absolute.*Docker"):
                        preview.seed_site("fs-e2e-preview-test", "tenant-web", "/bench", {})
                    run.assert_not_called()

    def test_container_fixture_reaches_keycloak_without_a_host_tunnel(self):
        project = "fs-e2e-preview-browser-test"
        settings = {"E2E_BROWSER_RUNTIME": "container", "FS_COLIMA_PROFILE": "factory", "PREVIEW_PROJECT": project}
        response = subprocess.CompletedProcess([], 0, json.dumps([200, None, json.dumps({"ready": True})]))
        with patch.dict(os.environ, settings), patch.object(fixtures, "DOCKER_PATH", "/tools/docker"), patch.object(
            fixtures.subprocess, "run", return_value=response,
        ) as run:
            self.assertEqual(fixtures.keycloak_request(43820, "/health", token="test-only-token"), {"ready": True})
        args, kwargs = run.call_args
        self.assertEqual(args[0][:6], ["/tools/docker", "--context", "colima-factory", "exec", "-i", project + "-tenant-web-1"])
        self.assertNotIn("test-only-token", str(args))
        self.assertEqual(json.loads(kwargs["input"])["headers"]["Authorization"], "Bearer test-only-token")

    def test_live_credentials_are_split_between_tenant_clients(self):
        claims = base64.urlsafe_b64encode(json.dumps({
            "aud": "identity-sync", "azp": "site-tenant1-service",
        }).encode()).decode().rstrip("=")
        settings = {
            "E2E_KEYCLOAK_CLIENT_SECRET": "browser-secret",
            "E2E_KEYCLOAK_SERVICE_CLIENT_SECRET": "service-secret",
        }
        with patch.dict(os.environ, settings), patch.object(
            fixtures, "keycloak_request", side_effect=[
                {"error": "unauthorized_client"},
                {"error": "unauthorized_client"},
                {"access_token": f"header.{claims}.signature"},
            ],
        ) as request:
            fixtures.check_tenant_clients(43820)
        forms = [call.kwargs["data"] for call in request.call_args_list]
        self.assertEqual([form["client_id"] for form in forms], [
            "site-tenant1", "site-tenant1", "site-tenant1-service",
        ])
        self.assertEqual([form.get("scope") for form in forms], [None, "aud-identity-sync", "aud-identity-sync"])
        self.assertEqual([form["client_secret"] for form in forms], [
            "browser-secret", "browser-secret", "service-secret",
        ])

    def test_browser_service_grant_success_stops_the_preview(self):
        settings = {
            "E2E_KEYCLOAK_CLIENT_SECRET": "browser-secret",
            "E2E_KEYCLOAK_SERVICE_CLIENT_SECRET": "service-secret",
        }
        with patch.dict(os.environ, settings), patch.object(
            fixtures, "keycloak_request", return_value={"access_token": "unexpected"},
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "browser client did not refuse"):
                fixtures.check_tenant_clients(43820)
            request.assert_called_once()

    def test_sync_user_creation_requires_a_location(self):
        settings = {
            "E2E_KEYCLOAK_ADMIN_USER": "preview-admin",
            "E2E_KEYCLOAK_ADMIN_PASSWORD": "synthetic",
        }
        with patch.dict(os.environ, settings), patch.object(
            fixtures, "keycloak_request",
            side_effect=[{"access_token": "synthetic"}, None, None],
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "missing a Location header for the test user"):
                fixtures.seed_keycloak(43820, "synthetic")
            self.assertEqual(request.call_count, 3)

    def test_lifecycle_accounts_have_dedicated_credentials_and_subjects(self):
        settings = {
            "E2E_KEYCLOAK_ADMIN_USER": "preview-admin",
            "E2E_KEYCLOAK_ADMIN_PASSWORD": "synthetic",
        }
        calls = []

        def request(port, route, **kwargs):
            if route.endswith("/token"):
                return {"access_token": "synthetic"}
            calls.append((route, kwargs["data"]))
            return "http://localhost/entries/" + str(len(calls))

        with patch.dict(os.environ, settings), patch.object(fixtures, "keycloak_request", side_effect=request):
            _, lifecycle = fixtures.seed_keycloak(43820, "synthetic")

        self.assertEqual(set(lifecycle), {"delete", "revoke", "employee"})
        self.assertEqual(len({account["password"] for account in lifecycle.values()}), 3)
        for name, account in lifecycle.items():
            self.assertEqual(account["email"], f"e2e-{name}-preview@example.test")
            self.assertTrue(account["subject"])
        members = [data for route, data in calls if route.endswith("/members")]
        self.assertEqual(members, ["2", lifecycle["delete"]["subject"], lifecycle["revoke"]["subject"]])

    def test_loopback_provider_is_rejected_before_fixtures_are_seeded(self):
        settings = {
            "PREVIEW_PROJECT": "fs-e2e-preview-fixture-test",
            "PANE_PORT": "43820",
            "E2E_PROVIDER_IP": "127.0.0.1",
        }
        with patch.dict(os.environ, settings), patch.object(
            fixtures, "seed_keycloak",
        ) as seed, patch.object(fixtures, "seed_site"):
            with self.assertRaisesRegex(SystemExit, "private address on the preview network"):
                fixtures.main()
            seed.assert_not_called()

    def test_full_browser_accounts_are_distinct_and_only_otp_accounts_enroll(self):
        accounts = fixtures.browser_keycloak.browser_accounts()
        self.assertEqual(len(accounts), 12)
        self.assertEqual(len({account["email"] for account in accounts.values()}), 12)
        self.assertEqual(len({account["password"] for account in accounts.values()}), 12)
        enrolled = {key for key, account in accounts.items() if "otp_seed" in account}
        self.assertEqual(enrolled, {"chromium_magic-otp", "webkit_magic-otp"})
        seeds = [accounts[key]["otp_seed"] for key in enrolled]
        self.assertNotEqual(*seeds)
        credential = fixtures.browser_keycloak.otp_credential(seeds[0])
        self.assertEqual(json.loads(credential["secretData"])["value"], base64.b32decode(seeds[0]).decode())
        self.assertEqual(json.loads(credential["credentialData"])["period"], 30)

    def test_browser_client_configuration_grants_the_reader_only_view_users(self):
        responses = {
            "/client-scopes": [
                {"name": "mobile", "id": "mobile-scope"},
                {"name": "kc-admin-api", "id": "admin-api-scope"},
                {"name": "aud-site-tenant1", "id": "tenant-scope"},
            ],
            "/clients?clientId=mobile-app": [{"id": "mobile", "attributes": {}}],
            "/clients?clientId=e2e-expired-mobile": [{"id": "expired"}],
            "/clients/mobile/default-client-scopes": [{"id": "roles-scope", "name": "roles"}],
            "/clients/expired/default-client-scopes": [],
            "/authentication/flows/atonota-browser-magic-link/executions": [
                {"providerId": "magiclink", "authenticationConfig": "magic"},
                {"providerId": "conditional-user-configured", "authenticationConfig": "other"},
            ],
            "/authentication/config/magic": {"id": "magic", "config": {}},
            "/clients?clientId=e2e-browser-reader": [{"id": "reader"}],
            "/clients?clientId=realm-management": [{"id": "management"}],
            "/clients/reader/service-account-user": {"id": "reader-user"},
            "/clients/management/roles/view-users": {"id": "view", "name": "view-users"},
        }
        calls = []

        def call(path, **kwargs):
            calls.append((path, kwargs))
            return responses.get(path)

        redirect = "http://127.0.0.1:43828/callback"
        reader, secret = fixtures.browser_keycloak.configure_browser_clients(call, redirect)
        self.assertEqual(reader, "e2e-browser-reader")
        self.assertTrue(secret)
        self.assertIn(("/clients/mobile/default-client-scopes/roles-scope", {"method": "DELETE"}), calls)
        self.assertIn(("/clients/mobile/optional-client-scopes/tenant-scope", {"method": "PUT", "data": {}}), calls)
        self.assertIn(("/clients/reader/default-client-scopes/admin-api-scope", {"method": "PUT", "data": {}}), calls)
        role = {"id": "view", "name": "view-users"}
        grants = [(path, values["data"]) for path, values in calls if "/clients/management" in path and "data" in values]
        self.assertEqual(grants, [
            ("/users/reader-user/role-mappings/clients/management", [role]),
            ("/clients/reader/scope-mappings/clients/management", [role]),
        ])
