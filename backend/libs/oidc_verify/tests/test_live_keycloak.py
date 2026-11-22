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
from unittest.mock import patch

from oidc_verify import JwksCache, TokenError, verify_access_token, verify_logout_token

KC = os.environ.get("KC_PUBLIC_URL", "")
SECRET = os.environ.get("ATONOTA_IDENTITY_SYNC_SECRET", "")
ISS = f"{KC}/realms/platform"

# Sample tenant scope and audience from contracts.md, section 2.
TENANT_SCOPE = "aud-site-tenant1"
TENANT_AUDIENCE = "site-tenant1"


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


@unittest.skipUnless(KC and SECRET, "Live test requires KC_PUBLIC_URL and ATONOTA_IDENTITY_SYNC_SECRET")
class LiveKeycloakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parts = local_issuer_parts(ISS)
        cls.cache = JwksCache(
            f"http://127.0.0.1:{parts.port}{parts.path}/protocol/openid-connect/certs",
            ttl_seconds=600,
        )

    def test_live_service_token_validates(self):
        token = get_token("identity-sync", SECRET, TENANT_SCOPE)
        claims = verify_access_token(
            token,
            cache=self.cache,
            issuer=ISS,
            audience=TENANT_AUDIENCE,
            allowed_azp={"identity-sync"},
            leeway=30,
        )
        self.assertEqual(claims["azp"], "identity-sync")
        self.assertEqual(claims["aud"], TENANT_AUDIENCE)

    def test_live_token_rejects_wrong_audience(self):
        token = get_token("identity-sync", SECRET, TENANT_SCOPE)
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
                audience=TENANT_AUDIENCE,
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
            f"{TENANT_SCOPE} aud-press",
            (TENANT_AUDIENCE, "press"),
        )
        self.assert_combined_scope_rejected(
            "identity-sync",
            SECRET,
            f"{TENANT_SCOPE} admin-api kc-admin-api",
            (TENANT_AUDIENCE,),
        )

    @unittest.skipUnless(os.environ.get("ATONOTA_PRESS_SERVICE_SECRET"), "Press service secret is required")
    def test_press_service_combined_scope_token_is_refused(self):
        self.assert_combined_scope_rejected(
            "press-service",
            os.environ["ATONOTA_PRESS_SERVICE_SECRET"],
            f"{TENANT_SCOPE} aud-identity-sync",
            (TENANT_AUDIENCE, "identity-sync"),
        )

    def test_live_token_is_not_logout_token(self):
        token = get_token("identity-sync", SECRET, TENANT_SCOPE)
        with self.assertRaises(TokenError) as caught:
            verify_logout_token(token, cache=self.cache, issuer=ISS, client_id=TENANT_AUDIENCE)
        self.assertEqual(caught.exception.code, "not_logout_token")

    def test_key_list_comes_from_live_endpoint(self):
        token = get_token("identity-sync", SECRET, "aud-press")
        claims = verify_access_token(
            token, cache=self.cache, issuer=ISS, audience="press", allowed_azp={"identity-sync"}
        )
        self.assertEqual(claims["iss"], ISS)


if __name__ == "__main__":
    unittest.main()
