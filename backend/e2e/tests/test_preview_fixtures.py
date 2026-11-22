"""Check fixture failures without starting Keycloak, Docker, or Frappe."""

import os
import unittest
from unittest.mock import patch

from backend.e2e.preview import fixtures


class PreviewFixturesTest(unittest.TestCase):
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
