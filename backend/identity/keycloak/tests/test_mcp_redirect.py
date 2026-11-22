"""Check that the MCP client can use only an exact secure callback."""

from __future__ import annotations

import json
import os
import unittest
from urllib.parse import urlencode, urlsplit

from helpers import admin, admin_token, get_environment_value, pkce_pair, read_realm, request, safe_detail

CLIENT_ID = "mcp-external"
POLICY = "mcp-external-security"
POLICY_MARKER = "mcp.external-client"
REGISTRATION_POLICY = "mcp-redirect-registration"


class McpRedirectRealmTest(unittest.TestCase):
    def test_redirect_policy_only_applies_to_designated_external_clients(self):
        realm = read_realm()
        marked = [
            client["clientId"]
            for client in realm["clients"]
            if client.get("attributes", {}).get(POLICY_MARKER) == "true"
        ]
        self.assertEqual(marked, [CLIENT_ID])

        policies = realm["clientPolicies"]["policies"]
        policy = next((item for item in policies if item["name"] == POLICY), None)
        self.assertIsNotNone(policy)
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["profiles"], [POLICY])
        conditions = policy["conditions"]
        self.assertEqual(len(conditions), 1)
        self.assertEqual(conditions[0]["condition"], "client-attributes")
        self.assertEqual(
            json.loads(conditions[0]["configuration"]["attributes"]), [{"key": POLICY_MARKER, "value": "true"}]
        )
        profiles = realm["clientProfiles"]["profiles"]
        profile = next(item for item in profiles if item["name"] == POLICY)
        self.assertIn("mcp-exact-redirect", {item["executor"] for item in profile["executors"]})

    def test_registration_policy_uses_only_the_redirect_executor(self):
        realm = read_realm()
        policy = next(
            (item for item in realm["clientPolicies"]["policies"] if item["name"] == REGISTRATION_POLICY), None
        )
        self.assertIsNotNone(policy)
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["profiles"], [REGISTRATION_POLICY])
        self.assertEqual([item["condition"] for item in policy["conditions"]], ["client-updater-context"])
        profile = next(item for item in realm["clientProfiles"]["profiles"] if item["name"] == REGISTRATION_POLICY)
        self.assertEqual([item["executor"] for item in profile["executors"]], ["mcp-exact-redirect"])


@unittest.skipUnless(os.environ.get("KC_MCP_TEST"), "isolated MCP realm not configured")
class McpRedirectKeycloakTest(unittest.TestCase):
    def setUp(self):
        self.issuer = get_environment_value("KC_PUBLIC_URL") + "/realms/platform"
        self.redirect = get_environment_value("ATONOTA_MCP_REDIRECT_URI")
        self.resource = get_environment_value("ATONOTA_MCP_RESOURCE_URL")
        self.admin_token = admin_token()
        clients = admin("/clients?" + urlencode({"clientId": CLIENT_ID}), self.admin_token)
        self.assertEqual(clients.status, 200)
        matched = [item for item in clients.json() if item["clientId"] == CLIENT_ID]
        self.assertEqual(len(matched), 1)
        self.client_path = f"/clients/{matched[0]['id']}"
        self.original_redirects = matched[0]["redirectUris"]
        self.addCleanup(self.restore_redirects)

    def restore_redirects(self):
        result = admin(self.client_path, admin_token(), method="PUT", body={"redirectUris": self.original_redirects})
        self.assertEqual(result.status, 204, safe_detail(result))

    def set_redirect(self, redirect):
        return admin(self.client_path, self.admin_token, method="PUT", body={"redirectUris": [redirect]})

    def authorize(self, redirect):
        _, challenge = pkce_pair()
        query = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "scope": "mcp",
            "resource": self.resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if redirect is not None:
            query["redirect_uri"] = redirect
        return request("GET", f"{self.issuer}/protocol/openid-connect/auth?" + urlencode(query))

    def assert_refused_before_login(self, response):
        self.assertEqual(response.status, 400, safe_detail(response))
        self.assertFalse(response.headers.get("Location"), "Unsafe callback must not receive an error")
        self.assertNotIn(b'name="username"', response.body)

    def test_unsafe_configured_callback_cannot_be_saved(self):
        cases = (
            ("https://client.example.test/*", "https://client.example.test/other"),
            ("http://client.example.test/callback", "http://client.example.test/callback"),
            ("https://user@client.example.test/callback", "https://user@client.example.test/callback"),
            ("https://client.example.test/callback#fragment", "https://client.example.test/callback#fragment"),
            ("https://client.example.test/%2a", "https://client.example.test/%2a"),
        )
        for configured, requested in cases:
            with self.subTest(configured=configured):
                saved = self.set_redirect(configured)
                self.assertEqual(saved.status, 400, safe_detail(saved))
                self.assert_refused_before_login(self.authorize(requested))
        self.assertEqual(self.authorize(self.redirect).status, 200)

    def test_only_tagged_clients_are_subject_to_mcp_registration_rule(self):
        candidate = {
            "protocol": "openid-connect",
            "publicClient": True,
            "enabled": False,
            "standardFlowEnabled": True,
            "redirectUris": ["https://client.example.test/*"],
        }
        tagged = admin(
            "/clients",
            self.admin_token,
            method="POST",
            body={**candidate, "clientId": "mcp-tagged-registration-test", "attributes": {POLICY_MARKER: "true"}},
        )
        self.clean_up_created_client(tagged)
        self.assertEqual(tagged.status, 400, safe_detail(tagged))

        untagged = admin(
            "/clients",
            self.admin_token,
            method="POST",
            body={**candidate, "clientId": "mcp-untagged-registration-test"},
        )
        self.clean_up_created_client(untagged)
        self.assertEqual(untagged.status, 201, safe_detail(untagged))

    def clean_up_created_client(self, response):
        if response.status == 201:
            client_id = urlsplit(response.headers["Location"]).path.rsplit("/", 1)[-1]
            self.addCleanup(lambda: admin(f"/clients/{client_id}", admin_token(), method="DELETE"))

    def test_registered_https_callback_is_exact_and_required(self):
        registered = "https://client.example.test/callback"
        saved = self.set_redirect(registered)
        self.assertEqual(saved.status, 204, safe_detail(saved))
        valid = self.authorize(registered)
        self.assertEqual(valid.status, 200, safe_detail(valid))
        self.assert_refused_before_login(self.authorize(registered + "/other"))
        self.assert_refused_before_login(self.authorize(None))

    def test_loopback_port_and_path_are_exact(self):
        registered = urlsplit(self.redirect)
        self.assertEqual(registered.scheme, "http")
        self.assertIn(registered.hostname, {"localhost", "127.0.0.1"})
        self.assertEqual(self.authorize(self.redirect).status, 200)
        another_port = registered._replace(netloc=f"{registered.hostname}:{registered.port + 1}").geturl()
        self.assert_refused_before_login(self.authorize(another_port))
        self.assert_refused_before_login(self.authorize(self.redirect + "/other"))
