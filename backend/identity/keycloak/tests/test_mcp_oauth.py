"""Acceptance coverage for decision 0017 on the pinned Keycloak version."""

from __future__ import annotations

import os
import unittest
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from helpers import (
    HttpResponse,
    admin,
    admin_token,
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


class ConsentForm(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.action = None
        self.code = None
        self.feed(body.decode())

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        action = attributes.get("action") or ""
        if tag == "form" and "/login-actions/consent" in action:
            self.action = action
        if self.action and tag == "input" and attributes.get("name") == "code":
            self.code = attributes.get("value")


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

    def test_external_client_requires_user_consent_for_mcp_scope(self):
        scopes = {scope["name"]: scope for scope in self.realm["clientScopes"]}
        self.assertIs(self.clients[CLIENT].get("consentRequired"), True)
        self.assertEqual(scopes["mcp"]["attributes"]["display.on.consent.screen"], "true")

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
        self.assertEqual(self.clients[CLIENT]["defaultClientScopes"], ["acr", "basic"])
        mappers = scopes["mcp"]["protocolMappers"]
        by_type = {mapper["protocolMapper"]: mapper for mapper in mappers}
        self.assertEqual(by_type["oidc-audience-mapper"]["config"]["included.client.audience"], RESOURCE_CLIENT)
        self.assertIn("mcp-explicit-resource", by_type)
        self.assertEqual(self.clients[CLIENT]["attributes"]["mcp.expected-resource"], RESOURCE_SETTING)


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

    def authenticate(self, response):
        if response.status == 200 and not ConsentForm(response.body).action:
            action = _form_action(response.body.decode())
            form = urlencode(
                {
                    "username": get_environment_value("KC_MCP_TEST_USER"),
                    "password": get_environment_value("KC_MCP_TEST_PASSWORD"),
                }
            )
            response = self.browse(action, form.encode("ascii"))
        return self.follow_login_redirects(response)

    def follow_login_redirects(self, response):
        for _ in range(5):
            location = response.headers.get("Location", "")
            if response.status not in (302, 303) or not location.startswith(self.issuer + "/login-actions/"):
                break
            response = self.browse(location)
        return response

    def submit_consent(self, response, choice):
        consent = ConsentForm(response.body)
        self.assertTrue(consent.action and consent.code, "Expected Keycloak consent form")
        data = urlencode({"code": consent.code, choice: "true"}).encode("ascii")
        action = urljoin(self.issuer + "/", consent.action)
        return self.follow_login_redirects(self.browse(action, data))

    def login(self, response):
        response = self.authenticate(response)
        if response.status == 200 and ConsentForm(response.body).action:
            response = self.submit_consent(response, "accept")
        return self.callback(response)

    def callback(self, response):
        self.assertEqual(response.status, 302, safe_detail(response))
        return parse_qs(urlsplit(response.headers.get("Location", "")).query)

    def test_user_grants_or_denies_consent_before_mcp_code_is_issued(self):
        # A new browser does not erase the fixture user's grant from earlier tests.
        token = admin_token()
        query = urlencode({"username": get_environment_value("KC_MCP_TEST_USER"), "exact": "true"})
        users = admin(f"/users?{query}", token)
        self.assertEqual(users.status, 200, safe_detail(users))
        matches = users.json()
        self.assertEqual(len(matches), 1)
        reset = admin(f"/users/{matches[0]['id']}/consents/{CLIENT}", token, method="DELETE")
        self.assertIn(reset.status, (204, 404), safe_detail(reset))

        pending = self.authenticate(self.authorize())
        self.assertEqual(pending.status, 200, safe_detail(pending))
        self.assertIn(b"External MCP client", pending.body)
        declined = self.callback(self.submit_consent(pending, "cancel"))
        self.assertEqual(declined.get("error"), ["access_denied"])
        self.assertNotIn("code", declined.keys())

        pending = self.authenticate(self.authorize())
        self.assertEqual(pending.status, 200, safe_detail(pending))
        approved = self.callback(self.submit_consent(pending, "accept"))
        self.assertIn("code", approved.keys())
        response = self.exchange(approved["code"][0])
        self.assertEqual(response.status, 200, safe_detail(response))
        self.assertEqual(jwt_payload(response.json()["access_token"]).get("acr"), "employee")

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
        self.assertEqual(claims.get("mcp_resource"), self.resource)
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
        for source, target, error in (
            (wrong, wrong, "invalid_grant"),
            (self.resource, wrong, "invalid_grant"),
            (wrong, self.resource, "invalid_target"),
        ):
            result = self.exchange(self.code(resource=source), resource=target)
            self.assertEqual(result.status, 400, safe_detail(result))
            self.assertEqual(result.json().get("error"), error)

    def test_code_exchange_requires_an_explicit_resource(self):
        for authorization_resource in (self.resource, None):
            with self.subTest(authorization_resource=authorization_resource):
                response = self.exchange(self.code(resource=authorization_resource), resource=None)
                self.assertEqual(response.status, 400, safe_detail(response))
                self.assertEqual(response.json().get("error"), "invalid_grant")

    def test_code_exchange_cannot_add_a_resource_not_bound_to_the_code(self):
        response = self.exchange(self.code(resource=None))
        self.assertEqual(response.status, 400, safe_detail(response))
        self.assertEqual(response.json().get("error"), "invalid_target")

    def test_code_exchange_does_not_normalize_the_requested_resource(self):
        response = self.exchange(self.code(), resource=self.resource + "\n")
        self.assertEqual(response.status, 400, safe_detail(response))
        self.assertEqual(response.json().get("error"), "invalid_grant")

    def test_code_exchange_does_not_normalize_the_callback(self):
        response = self.exchange(self.code(), redirect_uri=self.redirect + "\n")
        self.assertEqual(response.status, 400, safe_detail(response))
        self.assertEqual(response.json().get("error"), "invalid_grant")

    def test_refresh_requires_an_explicit_resource(self):
        response = self.exchange(self.code())
        self.assertEqual(response.status, 200, safe_detail(response))
        denied = request(
            "POST",
            token_endpoint(),
            form={
                "client_id": CLIENT,
                "grant_type": "refresh_token",
                "refresh_token": response.json()["refresh_token"],
            },
        )
        self.assertEqual(denied.status, 400, safe_detail(denied))
        self.assertEqual(denied.json().get("error"), "invalid_target")

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
        self.assertEqual(jwt_payload(first.json()["access_token"]).get("mcp_resource"), self.resource)
        self.assertTrue(first.json()["refresh_token"] != previous)
        replay = refresh()
        self.assertEqual(replay.status, 400, safe_detail(replay))
        self.assertEqual(replay.json().get("error"), "invalid_grant")
