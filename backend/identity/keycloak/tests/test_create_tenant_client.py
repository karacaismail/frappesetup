"""Exercise the operator command without contacting Keycloak."""

import json
import runpy
import unittest
import uuid
from unittest.mock import MagicMock, patch

from yardimci import KLASOR, admin, canli_var_mi, safe_detail, yonetici_belirteci

COMMAND = KLASOR / "bin" / "create-tenant-client.py"
ARGS = ["acme", "https://tenant.example.test", "https://identity.example.test"]


class CreateTenantClientTest(unittest.TestCase):
    def run_command(self, args=ARGS, *, tty=True, reply="CREATE site-acme", status=201):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = status
        with (
            patch("sys.argv", [str(COMMAND), *args]),
            patch("sys.stdin.isatty", return_value=tty),
            patch("sys.stderr.isatty", return_value=tty),
            patch("builtins.input", return_value=reply),
            patch("builtins.print") as output,
            patch("getpass.getpass", return_value="dummy-admin-token") as token_prompt,
            patch("urllib.request.build_opener", return_value=opener),
        ):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(COMMAND), run_name="__main__")
        return stopped.exception.code, opener, output, token_prompt

    def test_preview_is_available_without_terminal_or_credentials(self):
        code, opener, output, prompt = self.run_command([*ARGS, "--preview"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("site-acme", str(output.call_args_list))
        opener.open.assert_not_called()
        prompt.assert_not_called()

    def test_declined_creation_never_requests_token_or_calls_keycloak(self):
        code, opener, _, prompt = self.run_command(reply="no")
        self.assertEqual(code, 2)
        opener.open.assert_not_called()
        prompt.assert_not_called()

    def test_noninteractive_creation_is_refused(self):
        code, opener, _, prompt = self.run_command(tty=False)
        self.assertEqual(code, 2)
        opener.open.assert_not_called()
        prompt.assert_not_called()

    def test_confirmed_creation_posts_restricted_client_to_admin_api(self):
        code, opener, output, prompt = self.run_command()
        self.assertEqual(code, 0)
        prompt.assert_called_once()
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://identity.example.test/admin/realms/platform/clients")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer dummy-admin-token")
        client = json.loads(request.data)
        self.assertEqual(client["clientId"], "site-acme")
        self.assertFalse(client["publicClient"])
        self.assertFalse(client["fullScopeAllowed"])
        self.assertFalse(client["directAccessGrantsEnabled"])
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertEqual(client["optionalClientScopes"], ["aud-identity-sync"])
        self.assertEqual(
            client["redirectUris"],
            [
                "https://tenant.example.test/api/method/platform_core.api.auth.keycloak_callback",
            ],
        )
        self.assertNotIn("secret", client)
        self.assertNotIn("dummy-admin-token", str(output.call_args_list))

    def test_conflict_prints_status_without_retrying(self):
        code, opener, output, _ = self.run_command(status=409)
        self.assertEqual(code, 1)
        opener.open.assert_called_once()
        self.assertIn("HTTP 409. site-acme already exists.", str(output.call_args_list))

    def test_redirect_handler_refuses_to_forward_the_token(self):
        command = runpy.run_path(str(COMMAND))
        handler = command["NoRedirect"]()
        self.assertIsNone(handler.redirect_request(None, None, 307, "", {}, "https://other.example.test"))

    def test_invalid_origins_are_rejected_without_network_access(self):
        for invalid in (
            "http://tenant.example.test",
            "https://*.example.test",
            "https://tenant.example.test/x",
            "https://tenant.example.test?secret=1",
            "https://user@tenant.example.test",
        ):
            with self.subTest(invalid=invalid):
                code, opener, _, prompt = self.run_command(["acme", invalid, ARGS[2]])
                self.assertEqual(code, 2)
                opener.open.assert_not_called()
                prompt.assert_not_called()


@unittest.skipUnless(canli_var_mi(), "Keycloak development environment is required")
class LiveTenantClientTest(unittest.TestCase):
    def test_keycloak_creates_the_client_with_a_secret_and_tenant_scopes(self):
        generate = runpy.run_path(str(COMMAND))["tenant_client"]
        slug = f"fixture-{uuid.uuid4().hex}"
        client_id = f"site-{slug}"
        client = json.loads(generate(slug, ARGS[1]))
        token = yonetici_belirteci()

        def cleanup():
            response = admin(f"/clients?clientId={client_id}", token)
            self.assertEqual(response.durum, 200, safe_detail(response))
            for entry in response.json():
                if entry["clientId"] == client_id:
                    removed = admin(f"/clients/{entry['id']}", token, yontem="DELETE")
                    self.assertEqual(removed.durum, 204, safe_detail(removed))

        self.addCleanup(cleanup)
        response = admin("/clients", token, yontem="POST", govde=client)
        self.assertEqual(response.durum, 201, safe_detail(response))
        response = admin(f"/clients?clientId={client_id}", token)
        self.assertEqual(response.durum, 200, safe_detail(response))
        (created,) = response.json()
        self.assertEqual(created["clientId"], client_id)
        self.assertFalse(created["publicClient"])
        self.assertEqual(created["attributes"]["pkce.code.challenge.method"], "S256")
        scopes = admin(f"/clients/{created['id']}/optional-client-scopes", token)
        self.assertEqual(scopes.durum, 200, safe_detail(scopes))
        self.assertEqual([scope["name"] for scope in scopes.json()], ["aud-identity-sync"])
        secret = admin(f"/clients/{created['id']}/client-secret", token)
        self.assertEqual(secret.durum, 200, safe_detail(secret))
        self.assertTrue(bool(secret.json().get("value")), safe_detail(secret))
