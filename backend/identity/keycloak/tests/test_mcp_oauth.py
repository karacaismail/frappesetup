"""Acceptance coverage for decision 0017 on the pinned Keycloak version."""

from __future__ import annotations

import os
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from helpers import (
    HttpResponse,
    get_environment_value,
    jwt_payload,
    local_test_authority,
    pkce_pair,
    read_realm,
    request,
    safe_detail,
    token_endpoint,
)
from test_extensions import _cookie_opener, _form_action, _open

CLIENT = "mcp-external"
RESOURCE_CLIENT = "mcp-resource"
RESOURCE_SETTING = "${ATONOTA_MCP_RESOURCE_URL:https://tenant.example.test/api/method/platform_core.api.ai.mcp}"
REDIRECT_SETTING = "${ATONOTA_MCP_REDIRECT_URI:https://mcp-client.example.test/callback}"
INTROSPECTION_SECRET_SETTING = "${ATONOTA_MCP_INTROSPECTION_SECRET}"


class McpRealmTest(unittest.TestCase):
    def setUp(self):
        self.realm = read_realm()
        self.clients = {client["clientId"]: client for client in self.realm["clients"]}

    def test_registered_client_uses_only_code_with_s256_and_exact_callback(self):
        self.assertIn(CLIENT, self.clients)
        client = self.clients[CLIENT]
        self.assertFalse(client["enabled"])
        self.assertTrue(client["publicClient"])
        self.assertTrue(client["standardFlowEnabled"])
        for flow in ("implicitFlowEnabled", "directAccessGrantsEnabled", "serviceAccountsEnabled"):
            self.assertFalse(client[flow], flow)
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertEqual(client["redirectUris"], [REDIRECT_SETTING])
        self.assertTrue(self.realm["revokeRefreshToken"])
        self.assertEqual(self.realm["refreshTokenMaxReuse"], 0)

    def test_audience_is_bound_to_the_resource_and_scope(self):
        self.assertIn(RESOURCE_CLIENT, self.clients)
        self.assertIn(RESOURCE_SETTING, self.clients)
        resource = self.clients[RESOURCE_CLIENT]
        introspector = self.clients[RESOURCE_SETTING]
        self.assertEqual(resource["attributes"]["resource_url"], RESOURCE_SETTING)
        self.assertEqual(introspector["secret"], INTROSPECTION_SECRET_SETTING)
        self.assertFalse(introspector["publicClient"])
        for client in (resource, introspector):
            self.assertFalse(client["enabled"])
            for flow in (
                "standardFlowEnabled",
                "implicitFlowEnabled",
                "directAccessGrantsEnabled",
                "serviceAccountsEnabled",
            ):
                self.assertFalse(client[flow], flow)
        scopes = {scope["name"]: scope for scope in self.realm["clientScopes"]}
        self.assertIn("mcp", scopes)
        self.assertEqual(self.clients[CLIENT]["optionalClientScopes"], ["mcp"])
        self.assertEqual(self.clients[CLIENT]["defaultClientScopes"], ["basic"])
        mappers = scopes["mcp"]["protocolMappers"]
        self.assertEqual(len(mappers), 1)
        self.assertEqual(mappers[0]["protocolMapper"], "oidc-audience-mapper")
        self.assertEqual(mappers[0]["config"]["included.client.audience"], RESOURCE_CLIENT)


@unittest.skipUnless(os.environ.get("KC_MCP_TEST"), "isolated MCP realm not configured")
class McpKeycloakTest(unittest.TestCase):
    def setUp(self):
        self.issuer = get_environment_value("KC_PUBLIC_URL") + "/realms/platform"
        self.redirect = get_environment_value("ATONOTA_MCP_REDIRECT_URI")
        self.resource = get_environment_value("ATONOTA_MCP_RESOURCE_URL")
        self.verifier, self.challenge = pkce_pair()
        self.browser = _cookie_opener()

    def browse(self, address, data=None):
        local_test_authority(address)
        status, headers, body = _open(self.browser, address, data)
        return HttpResponse(status, body.encode(), headers)

    def authorize(self, **overrides):
        query = {
            "client_id": CLIENT,
            "redirect_uri": self.redirect,
            "response_type": "code",
            "scope": "mcp",
            "resource": self.resource,
            "code_challenge_method": "S256",
            "code_challenge": self.challenge,
        }
        query.update(overrides)
        params = urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
        return self.browse(f"{self.issuer}/protocol/openid-connect/auth?{params}")

    def login(self, response):
        if response.status == 200:
            action = _form_action(response.body.decode())
            form = urlencode(
                {
                    "username": get_environment_value("KC_MCP_TEST_USER"),
                    "password": get_environment_value("KC_MCP_TEST_PASSWORD"),
                }
            )
            response = self.browse(action, form.encode("ascii"))
        self.assertEqual(response.status, 302, safe_detail(response))
        return parse_qs(urlsplit(response.headers.get("Location", "")).query)

    def code(self, **overrides):
        callback = self.login(self.authorize(**overrides))
        self.assertIn("code", callback.keys())
        return callback["code"][0]

    def exchange(self, code, **overrides):
        form = {
            "grant_type": "authorization_code",
            "client_id": CLIENT,
            "redirect_uri": self.redirect,
            "resource": self.resource,
            "code_verifier": self.verifier,
            "code": code,
        }
        form.update(overrides)
        return request("POST", token_endpoint(), form={key: val for key, val in form.items() if val is not None})

    def introspect(self, token):
        return request(
            "POST",
            token_endpoint() + "/introspect",
            form={
                "client_id": self.resource,
                "client_secret": get_environment_value("ATONOTA_MCP_INTROSPECTION_SECRET"),
                "token": token,
                "token_type_hint": "access_token",
            },
        )

    def test_discovery_and_pkce_and_exact_redirect(self):
        discovery = request("GET", f"{self.issuer}/.well-known/openid-configuration")
        self.assertEqual(discovery.status, 200)
        self.assertIn("S256", discovery.json()["code_challenge_methods_supported"])
        redirect = urlsplit(self.redirect)
        different_port = redirect._replace(netloc=f"{redirect.hostname}:{redirect.port + 1}").geturl()
        for options in (
            {"code_challenge": None},
            {"code_challenge_method": "plain"},
            {"redirect_uri": self.redirect + "/wrong"},
            {"redirect_uri": different_port},
        ):
            with self.subTest(options=options):
                result = self.authorize(**options)
                self.assertNotIn(b'name="username"', result.body)
                self.assertFalse("code=" in result.headers.get("Location", ""), "Unexpected authorization code")
                self.assertIn(result.status, (302, 400))
        verifier, _ = pkce_pair()
        denied = self.exchange(self.code(), code_verifier=verifier)
        self.assertEqual(denied.status, 400, safe_detail(denied))
        self.assertEqual(denied.json().get("error"), "invalid_grant")

    def test_code_exchange_and_introspection_use_the_single_resource(self):
        response = self.exchange(self.code())
        self.assertEqual(response.status, 200, safe_detail(response))
        tokens = response.json()
        claims = jwt_payload(tokens["access_token"])
        self.assertTrue(claims["aud"] in (self.resource, [self.resource]))
        self.assertIn("mcp", claims["scope"].split())
        self.assertEqual(claims["azp"], CLIENT)
        self.assertTrue(claims["sid"])
        self.assertTrue(0 < claims["exp"] - claims["iat"] <= 300)
        introspection = self.introspect(tokens["access_token"])
        self.assertEqual(introspection.status, 200, safe_detail(introspection))
        active = introspection.json()
        self.assertIs(active.get("active"), True)
        self.assertTrue(active.get("sid") == claims["sid"], "Introspection must bind the same session")
        self.assertTrue(active.get("sub") == claims["sub"], "Introspection must bind the same subject")
        self.assertEqual(active.get("client_id"), CLIENT)
        self.assertTrue(active.get("username") == get_environment_value("KC_MCP_TEST_USER"))

    def test_logout_makes_access_token_inactive(self):
        response = self.exchange(self.code())
        self.assertEqual(response.status, 200, safe_detail(response))
        tokens = response.json()
        self.assertIs(self.introspect(tokens["access_token"]).json().get("active"), True)
        logout = request(
            "POST",
            f"{self.issuer}/protocol/openid-connect/logout",
            form={
                "client_id": CLIENT,
                "refresh_token": tokens["refresh_token"],
            },
        )
        self.assertEqual(logout.status, 204, safe_detail(logout))
        introspection = self.introspect(tokens["access_token"])
        self.assertEqual(introspection.status, 200, safe_detail(introspection))
        self.assertIs(introspection.json().get("active"), False)

    def test_bad_and_multiple_resources_are_refused(self):
        wrong = "https://another.example.test/mcp"
        for resources, error in (("/invalid", "invalid_target"), ([self.resource, wrong], "invalid_request")):
            result = self.authorize(resource=resources)
            self.assertEqual(result.status, 302, safe_detail(result))
            detail = parse_qs(urlsplit(result.headers.get("Location", "")).query)
            self.assertNotIn("code", detail.keys())
            self.assertEqual(detail.get("error"), [error])
        # Keycloak validates a well-formed resource URL against client configuration during exchange.
        for source, target in ((wrong, wrong), (self.resource, wrong), (wrong, self.resource)):
            result = self.exchange(self.code(resource=source), resource=target)
            self.assertEqual(result.status, 400, safe_detail(result))
            self.assertEqual(result.json().get("error"), "invalid_target")

    def test_omitting_resource_from_both_requests_does_not_mint_mcp_audience(self):
        response = self.exchange(self.code(resource=None), resource=None)
        self.assertEqual(response.status, 200, safe_detail(response))
        claims = jwt_payload(response.json()["access_token"])
        self.assertTrue(claims.get("aud") in (RESOURCE_CLIENT, [RESOURCE_CLIENT]))

    def test_omitting_mcp_scope_does_not_mint_mcp_audience(self):
        result = self.exchange(self.code(scope=None))
        self.assertEqual(result.status, 400, safe_detail(result))
        self.assertEqual(result.json().get("error"), "invalid_target")

    def test_refresh_rotation_rejects_the_previous_value(self):
        response = self.exchange(self.code())
        self.assertEqual(response.status, 200, safe_detail(response))
        previous = response.json()["refresh_token"]

        def refresh():
            return request(
                "POST",
                token_endpoint(),
                form={
                    "client_id": CLIENT,
                    "grant_type": "refresh_token",
                    "refresh_token": previous,
                    "resource": self.resource,
                },
            )

        first = refresh()
        self.assertEqual(first.status, 200, safe_detail(first))
        self.assertTrue(first.json()["refresh_token"] != previous)
        replay = refresh()
        self.assertEqual(replay.status, 400, safe_detail(replay))
        self.assertEqual(replay.json().get("error"), "invalid_grant")
