"""Integration test against a live Keycloak instance.

Verify a token issued by Keycloak. Skip the test if the environment variables are missing.
Load the environment from backend/identity/keycloak/bin/kc-dev.sh, then run the test from this directory.
"""

import http.client
import json
import os
import unittest
import urllib.parse
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from oidc_verify import JwksCache, TokenError, verify_access_token, verify_logout_token

KC = os.environ.get("KC_PUBLIC_URL", "")
SECRET = os.environ.get("ATONOTA_IDENTITY_SYNC_SECRET", "")
ISS = f"{KC}/realms/platform"


def local_issuer_parts(issuer):
    if any(ord(character) < 32 or ord(character) == 127 for character in issuer):
        raise ValueError("Expected a local test issuer")
    parts = urllib.parse.urlsplit(issuer)
    host = parts.hostname
    port = parts.port
    if (
        parts.scheme != "http"
        or host not in {"127.0.0.1", "localhost", "identity.localhost"}
        or not port
        or parts.netloc.lower() != f"{host}:{port}"
        or str(port) != os.environ.get("KC_PORT")
        or parts.path != "/realms/platform"
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Expected the local Keycloak test issuer and port")
    return parts


def get_token(client: str, secret: str, scope: str) -> str:
    parts = local_issuer_parts(ISS)
    jwks_payload = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": client, "client_secret": secret, "scope": scope}
    ).encode()
    # The fixed Keycloak alias is only an HTTP Host value. No redirect or proxy is used.
    with closing(http.client.HTTPConnection("127.0.0.1", parts.port, timeout=30)) as connection:
        connection.request(
            "POST",
            f"{parts.path}/protocol/openid-connect/token",
            body=jwks_payload,
            headers={"Host": parts.netloc, "Content-Type": "application/x-www-form-urlencoded"},
        )
        with connection.getresponse() as response:
            if response.status != 200:
                raise RuntimeError(f"Keycloak token request failed. HTTP {response.status}")
            return json.load(response)["access_token"]


class LocalTokenRequestTest(unittest.TestCase):
    def test_external_host_and_unexpected_port_are_refused(self):
        for issuer in ("http://example.test:5070/realms/platform", "http://127.0.0.1:5071/realms/platform"):
            with self.subTest(issuer=issuer), patch.dict(os.environ, {"KC_PORT": "5070"}, clear=True):
                with patch(f"{__name__}.ISS", issuer):
                    with patch(
                        "http.client.HTTPConnection", side_effect=AssertionError("Unexpected network request")
                    ):
                        with self.assertRaises(ValueError):
                            get_token("test-client", "dummy", "test-scope")

    def test_redirect_is_refused_without_opening_a_second_connection(self):
        with patch.dict(os.environ, {"KC_PORT": "5070"}, clear=True):
            with patch(f"{__name__}.ISS", "http://identity.localhost:5070/realms/platform"):
                with patch("http.client.HTTPConnection") as connect:
                    response = connect.return_value.getresponse.return_value.__enter__.return_value
                    response.status = 303
                    with self.assertRaisesRegex(RuntimeError, "HTTP 303"):
                        get_token("test-client", "dummy", "test-scope")
                    connect.assert_called_once_with("127.0.0.1", 5070, timeout=30)
                    connect.return_value.request.assert_called_once()


def read_realm_fixture():
    realm_file = Path(__file__).resolve().parents[3] / "identity/keycloak/realm/platform-realm.json"
    return json.loads(realm_file.read_text(encoding="utf-8"))


def tenant_service_scope(realm):
    """Resolve the sample tenant permission from contracts.md, section 2.

    Both service clients may request the scope. Its sole audience is the tenant
    browser client, which has a separate service client.
    """
    clients = {client["clientId"]: client for client in realm["clients"]}
    shared = set(clients["identity-sync"]["optionalClientScopes"]) & set(
        clients["press-service"]["optionalClientScopes"]
    )
    matches = []
    for scope in realm["clientScopes"]:
        if scope["name"] not in shared:
            continue
        mappers = scope.get("protocolMappers", [])
        if len(mappers) != 1 or mappers[0]["protocolMapper"] != "oidc-audience-mapper":
            continue
        config = mappers[0]["config"]
        audience = config.get("included.client.audience")
        if (
            audience in clients
            and clients[audience].get("standardFlowEnabled")
            and not clients[audience].get("serviceAccountsEnabled")
            and clients.get(f"{audience}-service", {}).get("serviceAccountsEnabled")
            and config.get("access.token.claim") == "true"
            and not config.get("included.custom.audience")
        ):
            matches.append((scope["name"], audience))
    if len(matches) != 1:
        raise ValueError("Expected one shared scope for the sample tenant browser audience")
    return matches[0]


class TenantScopeSelectionTest(unittest.TestCase):
    def test_scope_resolution_tolerates_a_renamed_realm_scope(self):
        realm = read_realm_fixture()
        old_scope, audience = tenant_service_scope(realm)
        new_scope = "renamed-for-test"
        for scope in realm["clientScopes"]:
            if scope["name"] == old_scope:
                scope["name"] = new_scope
        for client in realm["clients"]:
            optional = client.get("optionalClientScopes", [])
            client["optionalClientScopes"] = [new_scope if name == old_scope else name for name in optional]
        self.assertEqual(tenant_service_scope(realm), (new_scope, audience))

    def test_combined_requests_use_the_scope_declared_by_the_realm(self):
        case = LiveKeycloakTest()
        case.tenant_scope = "renamed-sample-scope"
        case.tenant_audience = "renamed-sample-site"
        with patch.object(case, "assert_combined_scope_rejected") as check:
            case.test_identity_sync_combined_scope_tokens_are_refused()
        self.assertEqual(
            [call.args[2:] for call in check.call_args_list],
            [
                ("renamed-sample-scope aud-press", ("renamed-sample-site", "press")),
                ("renamed-sample-scope admin-api kc-admin-api", ("renamed-sample-site",)),
            ],
        )


@unittest.skipUnless(KC and SECRET, "Live test requires KC_PUBLIC_URL and ATONOTA_IDENTITY_SYNC_SECRET")
class LiveKeycloakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parts = local_issuer_parts(ISS)
        cls.tenant_scope, cls.tenant_audience = tenant_service_scope(read_realm_fixture())
        cls.cache = JwksCache(
            f"http://127.0.0.1:{parts.port}{parts.path}/protocol/openid-connect/certs",
            ttl_seconds=600,
        )

    def test_live_service_token_validates(self):
        token = get_token("identity-sync", SECRET, self.tenant_scope)
        claims = verify_access_token(
            token,
            cache=self.cache,
            issuer=ISS,
            audience=self.tenant_audience,
            allowed_azp={"identity-sync"},
            leeway=30,
        )
        self.assertEqual(claims["azp"], "identity-sync")
        self.assertEqual(claims["aud"], self.tenant_audience)

    def test_live_token_rejects_wrong_audience(self):
        token = get_token("identity-sync", SECRET, self.tenant_scope)
        with self.assertRaises(TokenError) as caught:
            verify_access_token(
                token, cache=self.cache, issuer=ISS, audience="press", allowed_azp={"identity-sync"}
            )
        self.assertEqual(caught.exception.code, "wrong_audience")
        with self.assertRaises(TokenError) as caught:
            verify_access_token(
                token,
                cache=self.cache,
                issuer=ISS,
                audience=self.tenant_audience,
                allowed_azp={"press-service"},
            )
        self.assertEqual(caught.exception.code, "wrong_azp")

    def assert_combined_scope_rejected(self, client, secret, scope, targets):
        token = get_token(client, secret, scope)
        for target in targets:
            with self.subTest(client=client, scope=scope, target=target):
                with self.assertRaises(TokenError) as error:
                    verify_access_token(
                        token,
                        cache=self.cache,
                        issuer=ISS,
                        audience=target,
                        allowed_azp={client},
                    )
                self.assertEqual(error.exception.code, "wrong_audience")

    def test_identity_sync_combined_scope_tokens_are_refused(self):
        self.assert_combined_scope_rejected(
            "identity-sync",
            SECRET,
            f"{self.tenant_scope} aud-press",
            (self.tenant_audience, "press"),
        )
        self.assert_combined_scope_rejected(
            "identity-sync",
            SECRET,
            f"{self.tenant_scope} admin-api kc-admin-api",
            (self.tenant_audience,),
        )

    @unittest.skipUnless(os.environ.get("ATONOTA_PRESS_SERVICE_SECRET"), "Press service secret is required")
    def test_press_service_combined_scope_token_is_refused(self):
        self.assert_combined_scope_rejected(
            "press-service",
            os.environ["ATONOTA_PRESS_SERVICE_SECRET"],
            f"{self.tenant_scope} aud-identity-sync",
            (self.tenant_audience, "identity-sync"),
        )

    def test_live_token_is_not_logout_token(self):
        token = get_token("identity-sync", SECRET, self.tenant_scope)
        with self.assertRaises(TokenError) as caught:
            verify_logout_token(token, cache=self.cache, issuer=ISS, client_id=self.tenant_audience)
        self.assertEqual(caught.exception.code, "not_logout_token")

    def test_key_list_comes_from_live_endpoint(self):
        token = get_token("identity-sync", SECRET, "aud-press")
        claims = verify_access_token(
            token, cache=self.cache, issuer=ISS, audience="press", allowed_azp={"identity-sync"}
        )
        self.assertEqual(claims["iss"], ISS)


if __name__ == "__main__":
    unittest.main()
