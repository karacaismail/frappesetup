"""Canlı Keycloak ile bütünleşme testi.

Keycloak'ın verdiği gerçek belirteç kitaplıkla doğrulanır. Ortam değişkenleri yoksa test atlanır.
Çalıştırma: backend/identity/keycloak/bin/kc-dev.sh ortamını yükleyin ve bu klasörde testi koşun.
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
SIR = os.environ.get("ATONOTA_IDENTITY_SYNC_SECRET", "")
ISS = f"{KC}/realms/platform"


def local_issuer_parts(issuer):
    if any(ord(character) < 32 or ord(character) == 127 for character in issuer):
        raise ValueError("Expected a local test issuer")
    parts = urllib.parse.urlsplit(issuer)
    host = parts.hostname
    port = parts.port
    if (
        parts.scheme != "http"
        or host not in {"127.0.0.1", "localhost", "kimlik.localhost"}
        or not port
        or parts.netloc.lower() != f"{host}:{port}"
        or str(port) != os.environ.get("KC_PORT")
        or parts.path != "/realms/platform"
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Expected the local Keycloak test issuer and port")
    return parts


def belirtec_al(istemci: str, sir: str, kapsam: str) -> str:
    parts = local_issuer_parts(ISS)
    veri = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": istemci, "client_secret": sir, "scope": kapsam}
    ).encode()
    # The fixed Keycloak alias is only an HTTP Host value. No redirect or proxy is used.
    with closing(http.client.HTTPConnection("127.0.0.1", parts.port, timeout=30)) as connection:
        connection.request(
            "POST",
            f"{parts.path}/protocol/openid-connect/token",
            body=veri,
            headers={"Host": parts.netloc, "Content-Type": "application/x-www-form-urlencoded"},
        )
        with connection.getresponse() as yanit:
            if yanit.status != 200:
                raise RuntimeError(f"Keycloak token request failed. HTTP {yanit.status}")
            return json.load(yanit)["access_token"]


class LocalTokenRequestTest(unittest.TestCase):
    def test_external_host_and_unexpected_port_are_refused(self):
        for issuer in ("http://example.test:5070/realms/platform", "http://127.0.0.1:5071/realms/platform"):
            with self.subTest(issuer=issuer), patch.dict(os.environ, {"KC_PORT": "5070"}, clear=True):
                with patch(f"{__name__}.ISS", issuer):
                    with patch(
                        "http.client.HTTPConnection", side_effect=AssertionError("Unexpected network request")
                    ):
                        with self.assertRaises(ValueError):
                            belirtec_al("test-client", "dummy", "test-scope")

    def test_redirect_is_refused_without_opening_a_second_connection(self):
        with patch.dict(os.environ, {"KC_PORT": "5070"}, clear=True):
            with patch(f"{__name__}.ISS", "http://kimlik.localhost:5070/realms/platform"):
                with patch("http.client.HTTPConnection") as connect:
                    response = connect.return_value.getresponse.return_value.__enter__.return_value
                    response.status = 303
                    with self.assertRaisesRegex(RuntimeError, "HTTP 303"):
                        belirtec_al("test-client", "dummy", "test-scope")
                    connect.assert_called_once_with("127.0.0.1", 5070, timeout=30)
                    connect.return_value.request.assert_called_once()


@unittest.skipUnless(KC and SIR, "KC_PUBLIC_URL ve ATONOTA_IDENTITY_SYNC_SECRET yok, canlı test atlandı")
class CanliKeycloakTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parts = local_issuer_parts(ISS)
        cls.cache = JwksCache(
            f"http://127.0.0.1:{parts.port}{parts.path}/protocol/openid-connect/certs",
            ttl_seconds=600,
        )

    def test_gercek_servis_belirteci_dogrulanir(self):
        token = belirtec_al("identity-sync", SIR, "aud-site-kiraci1")
        claims = verify_access_token(
            token,
            cache=self.cache,
            issuer=ISS,
            audience="site-kiraci1",
            allowed_azp={"identity-sync"},
            leeway=30,
        )
        self.assertEqual(claims["azp"], "identity-sync")
        self.assertEqual(claims["aud"], "site-kiraci1")

    def test_gercek_belirtec_yanlis_hedefte_reddedilir(self):
        token = belirtec_al("identity-sync", SIR, "aud-site-kiraci1")
        with self.assertRaises(TokenError) as yakalanan:
            verify_access_token(
                token, cache=self.cache, issuer=ISS, audience="press", allowed_azp={"identity-sync"}
            )
        self.assertEqual(yakalanan.exception.code, "wrong_audience")
        with self.assertRaises(TokenError) as yakalanan:
            verify_access_token(
                token, cache=self.cache, issuer=ISS, audience="site-kiraci1", allowed_azp={"press-service"}
            )
        self.assertEqual(yakalanan.exception.code, "wrong_azp")

    def assert_combined_scope_rejected(self, client, secret, scope, targets):
        token = belirtec_al(client, secret, scope)
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
            SIR,
            "aud-site-kiraci1 aud-press",
            ("site-kiraci1", "press"),
        )
        self.assert_combined_scope_rejected(
            "identity-sync",
            SIR,
            "aud-site-kiraci1 admin-api kc-admin-api",
            ("site-kiraci1",),
        )

    @unittest.skipUnless(os.environ.get("ATONOTA_PRESS_SERVICE_SECRET"), "Press service secret is required")
    def test_press_service_combined_scope_token_is_refused(self):
        self.assert_combined_scope_rejected(
            "press-service",
            os.environ["ATONOTA_PRESS_SERVICE_SECRET"],
            "aud-site-kiraci1 aud-identity-sync",
            ("site-kiraci1", "identity-sync"),
        )

    def test_gercek_belirtec_cikis_belirteci_degil(self):
        token = belirtec_al("identity-sync", SIR, "aud-site-kiraci1")
        with self.assertRaises(TokenError) as yakalanan:
            verify_logout_token(token, cache=self.cache, issuer=ISS, client_id="site-kiraci1")
        self.assertEqual(yakalanan.exception.code, "not_logout_token")

    def test_anahtar_listesi_gercek_uctan_gelir(self):
        token = belirtec_al("identity-sync", SIR, "aud-press")
        claims = verify_access_token(
            token, cache=self.cache, issuer=ISS, audience="press", allowed_azp={"identity-sync"}
        )
        self.assertEqual(claims["iss"], ISS)


if __name__ == "__main__":
    unittest.main()
