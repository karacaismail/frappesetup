"""Canlı Keycloak ile bütünleşme testi.

Keycloak'ın verdiği gerçek belirteç kitaplıkla doğrulanır. Ortam değişkenleri yoksa test atlanır.
Çalıştırma: backend/identity/keycloak/bin/kc-dev.sh ortamını yükleyin ve bu klasörde testi koşun.
"""

import json
import os
import unittest
import urllib.parse
import urllib.request

from oidc_verify import JwksCache, TokenError, verify_access_token, verify_logout_token

KC = os.environ.get("KC_PUBLIC_URL", "")
SIR = os.environ.get("ATONOTA_IDENTITY_SYNC_SECRET", "")
ISS = f"{KC}/realms/platform"
JWKS = f"{ISS}/protocol/openid-connect/certs"


def belirtec_al(istemci: str, sir: str, kapsam: str) -> str:
    veri = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": istemci, "client_secret": sir, "scope": kapsam}
    ).encode()
    with urllib.request.urlopen(f"{ISS}/protocol/openid-connect/token", data=veri, timeout=30) as yanit:  # noqa: S310
        return json.load(yanit)["access_token"]


@unittest.skipUnless(KC and SIR, "KC_PUBLIC_URL ve ATONOTA_IDENTITY_SYNC_SECRET yok, canlı test atlandı")
class CanliKeycloakTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = JwksCache(JWKS, ttl_seconds=600)

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
