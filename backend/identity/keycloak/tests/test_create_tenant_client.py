"""Exercise the operator command without contacting Keycloak."""

import json
import runpy
import unittest
import uuid
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from yardimci import KLASOR, admin, canli_var_mi, istemci_belirteci, jwt_govdesi, ortam, safe_detail, yonetici_belirteci

COMMAND = KLASOR / "bin" / "create-tenant-client.py"
ARGS = ["acme", "https://tenant.example.test", "https://identity.example.test"]


class FakeKeycloak:
    def __init__(self):
        self.clients = {"identity-sync": {"id": "sync"}, "press-service": {"id": "press-service"}}
        self.scopes = {}
        self.optional = {client["id"]: set() for client in self.clients.values()}
        self.default = {client_id: set() for client_id in self.optional}
        self.calls = []
        self.deny = {}

    def open(self, request, *, timeout):
        parts = urlsplit(request.full_url)
        path = parts.path.removeprefix("/admin/realms/platform")
        method = request.get_method()
        self.calls.append(request)
        if code := self.deny.get((method, path)):
            raise HTTPError(request.full_url, code, "Denied", {}, BytesIO(b"synthetic denial"))
        body = json.loads(request.data) if request.data else None
        if method == "GET" and path == "/clients":
            query = parse_qs(parts.query)
            if "clientId" in query:
                name = query["clientId"][0]
                status, data = 200, [{"clientId": name, **self.clients[name]}] if name in self.clients else []
            else:
                first = int(query["first"][0])
                count = int(query["max"][0])
                all_clients = [{"clientId": name, **client} for name, client in self.clients.items()]
                status, data = 200, all_clients[first : first + count]
        elif method == "POST" and path == "/clients":
            client_id = body["clientId"]
            if client_id in self.clients:
                raise HTTPError(request.full_url, 409, "Conflict", {}, BytesIO())
            self.clients[client_id] = {**body, "id": "tenant", "secret": "preserved-test-secret"}
            status, data = 201, None
        elif method == "GET" and path == "/client-scopes":
            status, data = 200, list(self.scopes.values())
        elif method == "POST" and path == "/client-scopes":
            self.scopes[body["name"]] = {**body, "id": "scope"}
            status, data = 201, None
        elif method == "GET" and path.endswith("/protocol-mappers/models"):
            status, data = 200, self.scopes["aud-site-acme"]["protocolMappers"]
        elif method == "GET" and path.endswith("/scope-mappings"):
            status, data = 200, {}
        elif method == "GET" and path in ("/default-default-client-scopes", "/default-optional-client-scopes"):
            status, data = 200, []
        elif path.startswith("/clients/"):
            _, _, client, kind, *rest = path.split("/")
            if method == "GET":
                bindings = {"optional-client-scopes": self.optional, "default-client-scopes": self.default}
                status, data = 200, [{"id": scope} for scope in bindings[kind][client]]
            elif method == "PUT" and kind == "optional-client-scopes":
                self.optional[client].add(rest[0])
                status, data = 204, None
            else:
                raise AssertionError(f"Unexpected request {method} {path}")
        else:
            raise AssertionError(f"Unexpected request {method} {path}")
        response = MagicMock()
        response.__enter__.return_value.status = status
        response.__enter__.return_value.read.return_value = json.dumps(data).encode()
        return response


class CreateTenantClientTest(unittest.TestCase):
    def run_command(self, args=ARGS, *, tty=True, reply="CREATE site-acme", server=None):
        opener = MagicMock()
        if server is not None:
            opener.open.side_effect = server.open
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
        preview = str(output.call_args_list)
        for name in ("site-acme", "aud-site-acme", "identity-sync", "press-service", "optional"):
            self.assertIn(name, preview)
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
        server = FakeKeycloak()
        code, _, output, prompt = self.run_command(server=server)
        self.assertEqual(code, 0)
        prompt.assert_called_once()
        request = next(
            call for call in server.calls if call.get_method() == "POST" and call.full_url.endswith("/clients")
        )
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

    def test_confirmed_creation_installs_and_binds_only_an_optional_tenant_scope(self):
        server = FakeKeycloak()
        code, _, _, _ = self.run_command(server=server)
        self.assertEqual(code, 0)
        scope = server.scopes["aud-site-acme"]
        self.assertEqual(scope["protocol"], "openid-connect")
        self.assertEqual(scope["attributes"]["include.in.token.scope"], "false")
        (mapper,) = scope["protocolMappers"]
        self.assertEqual(mapper["protocolMapper"], "oidc-audience-mapper")
        self.assertEqual(mapper["config"]["included.client.audience"], "site-acme")
        self.assertEqual(mapper["config"]["access.token.claim"], "true")
        self.assertEqual(mapper["config"]["id.token.claim"], "false")
        self.assertEqual(server.optional, {"sync": {"scope"}, "press-service": {"scope"}})
        self.assertEqual(server.default, {"sync": set(), "press-service": set()})

    def test_rerun_preserves_secret_and_completes_missing_steps(self):
        server = FakeKeycloak()
        server.deny[("PUT", "/clients/press-service/optional-client-scopes/scope")] = 403
        code, _, output, _ = self.run_command(server=server)
        self.assertEqual(code, 1)
        self.assertIn("HTTP 403", str(output.call_args_list))
        self.assertEqual(server.optional["sync"], {"scope"})
        before = dict(server.clients["site-acme"])
        server.deny.clear()
        server.calls.clear()
        code, _, output, _ = self.run_command(server=server)
        self.assertEqual(code, 0)
        self.assertEqual(server.clients["site-acme"], before)
        self.assertNotIn(before["secret"], str(output.call_args_list))
        writes = [urlsplit(call.full_url).path for call in server.calls if call.get_method() != "GET"]
        self.assertEqual(writes, ["/admin/realms/platform/clients/press-service/optional-client-scopes/scope"])

    def test_rerun_creates_a_missing_scope_for_an_existing_client(self):
        server = FakeKeycloak()
        server.deny[("POST", "/client-scopes")] = 403
        self.assertEqual(self.run_command(server=server)[0], 1)
        self.assertEqual(server.scopes, {})
        before = dict(server.clients["site-acme"])
        server.calls.clear()
        server.deny.clear()

        self.assertEqual(self.run_command(server=server)[0], 0)
        self.assertEqual(server.clients["site-acme"], before)
        posts = [urlsplit(call.full_url).path for call in server.calls if call.get_method() == "POST"]
        self.assertEqual(posts, ["/admin/realms/platform/client-scopes"])
        self.assertEqual(server.optional, {"sync": {"scope"}, "press-service": {"scope"}})

    def test_rejects_a_conflicting_default_binding_before_writing_optional_bindings(self):
        server = FakeKeycloak()
        self.assertEqual(self.run_command(server=server)[0], 0)
        server.optional["sync"].clear()
        server.default["press-service"].add("scope")
        server.calls.clear()

        code, _, output, _ = self.run_command(server=server)
        self.assertEqual(code, 1)
        self.assertIn("already has a default binding", str(output.call_args_list))
        self.assertTrue(all(call.get_method() == "GET" for call in server.calls))

    def test_rejects_an_existing_scope_on_an_unrelated_client(self):
        server = FakeKeycloak()
        self.assertEqual(self.run_command(server=server)[0], 0)
        for index in range(100):
            server.clients[f"other-{index}"] = {"id": f"other-{index}"}
        server.clients["mobile-app"] = {"id": "mobile", "optionalClientScopes": ["aud-site-acme"]}
        server.optional["sync"].clear()
        server.calls.clear()

        code, _, output, _ = self.run_command(server=server)
        self.assertEqual(code, 1)
        self.assertIn("unexpected binding", str(output.call_args_list))
        self.assertTrue(all(call.get_method() == "GET" for call in server.calls))

    def test_refuses_to_reuse_a_tenant_client_without_pkce(self):
        server = FakeKeycloak()
        self.assertEqual(self.run_command(server=server)[0], 0)
        del server.clients["site-acme"]["attributes"]["pkce.code.challenge.method"]
        server.calls.clear()

        code, _, output, _ = self.run_command(server=server)
        self.assertEqual(code, 1)
        self.assertIn("does not match the requested tenant", str(output.call_args_list))
        self.assertTrue(all(call.get_method() == "GET" for call in server.calls))

    def test_rejects_401_and_403_without_creating_resources(self):
        for status in (401, 403):
            with self.subTest(status=status):
                server = FakeKeycloak()
                server.deny[("GET", "/clients")] = status
                code, _, output, _ = self.run_command(server=server)
                self.assertEqual(code, 1)
                self.assertIn(f"HTTP {status}", str(output.call_args_list))
                self.assertTrue(all(call.get_method() == "GET" for call in server.calls))
                self.assertNotIn("dummy-admin-token", str(output.call_args_list))
                self.assertNotIn("synthetic denial", str(output.call_args_list))

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
        command = runpy.run_path(str(COMMAND))
        slug = f"fixture-{uuid.uuid4().hex}"
        client_id = f"site-{slug}"
        client = command["tenant_client"](slug, ARGS[1])
        scope = command["tenant_scope"](client_id)
        token = yonetici_belirteci()

        def cleanup():
            cleanup_token = yonetici_belirteci()
            response = admin("/client-scopes", cleanup_token)
            self.assertEqual(response.durum, 200, safe_detail(response))
            for entry in response.json():
                if entry["name"] == scope["name"]:
                    removed = admin(f"/client-scopes/{entry['id']}", cleanup_token, yontem="DELETE")
                    self.assertEqual(removed.durum, 204, safe_detail(removed))
            response = admin(f"/clients?clientId={client_id}", cleanup_token)
            self.assertEqual(response.durum, 200, safe_detail(response))
            for entry in response.json():
                if entry["clientId"] == client_id:
                    removed = admin(f"/clients/{entry['id']}", cleanup_token, yontem="DELETE")
                    self.assertEqual(removed.durum, 204, safe_detail(removed))

        self.addCleanup(cleanup)
        request = command["make_admin_request"](ortam("KC_PUBLIC_URL"), token)
        command["provision_tenant"](request, client, scope)
        response = admin(f"/clients?clientId={client_id}", token)
        self.assertEqual(response.durum, 200, safe_detail(response))
        (created,) = response.json()
        self.assertEqual(created["clientId"], client_id)
        self.assertFalse(created["publicClient"])
        self.assertEqual(created["attributes"]["pkce.code.challenge.method"], "S256")
        secret_path = f"/clients/{created['id']}/client-secret"
        original_secret = request("GET", secret_path)["value"]
        self.assertTrue(bool(original_secret))
        command["provision_tenant"](request, client, scope)
        self.assertTrue(request("GET", secret_path)["value"] == original_secret)

        for name, secret_name in (
            ("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET"),
            ("press-service", "ATONOTA_PRESS_SERVICE_SECRET"),
        ):
            with self.subTest(client=name):
                response = istemci_belirteci(name, ortam(secret_name), scope["name"])
                self.assertEqual(response.durum, 200, safe_detail(response))
                claims = jwt_govdesi(response.json()["access_token"])
                self.assertEqual(claims["azp"], name)
                self.assertTrue(claims.get("aud") in (client_id, [client_id]))
                default = istemci_belirteci(name, ortam(secret_name))
                self.assertEqual(default.durum, 200, safe_detail(default))
                default_audience = jwt_govdesi(default.json()["access_token"]).get("aud", [])
                self.assertFalse(client_id in default_audience)
