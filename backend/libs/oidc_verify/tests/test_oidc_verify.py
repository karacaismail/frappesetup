"""oidc_verify birim testleri. Beklenen davranış docs/sozlesmeler.md 3. bölümünden alındı.

Anahtarlar yerelde üretilir. Ağ yoktur. JwksCache sahte sağlayıcıyla beslenir.
"""

import re
import time
import unittest
from pathlib import Path
from urllib.error import URLError

from keys import ISSUER, LOGOUT_EVENT, Anahtar, FakeJwks, access_payload, identity_payload, logout_payload

from oidc_verify import (
    JwksCache,
    JwksUnavailable,
    TokenError,
    verify_access_token,
    verify_id_token,
    verify_logout_token,
)

JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"


class Temel(unittest.TestCase):
    def setUp(self):
        self.anahtar = Anahtar("kid-1")
        self.provider = FakeJwks(self.anahtar)
        self.cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=self.provider)

    def access(self, token, **ek):
        ayar = {
            "cache": self.cache,
            "issuer": ISSUER,
            "audience": "site-tenant1",
            "allowed_azp": {"identity-sync"},
            "leeway": 30,
        }
        ayar.update(ek)
        return verify_access_token(token, **ayar)

    def error_code(self, islev, *args, **kwargs) -> str:
        with self.assertRaises(TokenError) as caught:
            islev(*args, **kwargs)
        return caught.exception.code


class AccessTokenTest(Temel):
    def test_returns_expected_token_claims(self):
        token = self.anahtar.sign(access_payload())
        fields = self.access(token)
        self.assertEqual(fields["sub"], "service-account-identity-sync")
        self.assertEqual(fields["aud"], "site-tenant1")
        self.assertEqual(fields["azp"], "identity-sync")

    def test_accepts_single_item_audience_list(self):
        token = self.anahtar.sign(access_payload(aud=["site-tenant1"]))
        self.assertEqual(self.access(token)["azp"], "identity-sync")

    def test_wrong_signature(self):
        baska = Anahtar("kid-1")
        token = baska.sign(access_payload())
        self.assertEqual(self.error_code(self.access, token), "invalid_signature")

    def test_none_algorithm(self):
        token = self.anahtar.sign(access_payload(), alg="none")
        self.assertEqual(self.error_code(self.access, token), "invalid_signature")

    def test_non_rs256_algorithm(self):
        token = self.anahtar.sign(access_payload(), alg="RS512")
        self.assertEqual(self.error_code(self.access, token), "invalid_signature")

    def test_invalid_token(self):
        self.assertEqual(self.error_code(self.access, "abc.def"), "malformed")
        self.assertEqual(self.error_code(self.access, ""), "malformed")
        self.assertEqual(self.error_code(self.access, "a.b.c"), "malformed")

    def test_missing_kid_is_malformed(self):
        import jwt

        token = jwt.encode(access_payload(), self.anahtar.private_pem, algorithm="RS256")
        self.assertEqual(self.error_code(self.access, token), "malformed")

    def test_wrong_iss(self):
        token = self.anahtar.sign(access_payload(iss=ISSUER + "x"))
        self.assertEqual(self.error_code(self.access, token), "wrong_issuer")
        token = self.anahtar.sign(access_payload(iss=None))
        self.assertEqual(self.error_code(self.access, token), "wrong_issuer")

    def test_wrong_aud(self):
        token = self.anahtar.sign(access_payload(aud="press"))
        self.assertEqual(self.error_code(self.access, token), "wrong_audience")
        token = self.anahtar.sign(access_payload(aud=None))
        self.assertEqual(self.error_code(self.access, token), "wrong_audience")

    def test_multiple_audiences_are_rejected(self):
        token = self.anahtar.sign(access_payload(aud=["site-tenant1", "account"]))
        self.assertEqual(self.error_code(self.access, token), "wrong_audience")

    def test_wrong_azp(self):
        token = self.anahtar.sign(access_payload(azp="press-service"))
        self.assertEqual(self.error_code(self.access, token), "wrong_azp")
        token = self.anahtar.sign(access_payload(azp=None))
        self.assertEqual(self.error_code(self.access, token), "wrong_azp")

    def test_accepts_an_allowed_authorized_party(self):
        token = self.anahtar.sign(access_payload(azp="press-service"))
        fields = self.access(token, allowed_azp={"identity-sync", "press-service"})
        self.assertEqual(fields["azp"], "press-service")

    def test_rejects_expired_token(self):
        simdi = int(time.time())
        token = self.anahtar.sign(access_payload(iat=simdi - 400, exp=simdi - 60))
        self.assertEqual(self.error_code(self.access, token), "expired")

    def test_valid_within_30_second_leeway(self):
        simdi = int(time.time())
        token = self.anahtar.sign(access_payload(iat=simdi - 300, exp=simdi - 20))
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        token = self.anahtar.sign(access_payload(iat=simdi - 300, exp=simdi - 40))
        self.assertEqual(self.error_code(self.access, token), "expired")

    def test_token_expires_without_clock_leeway(self):
        simdi = int(time.time())
        token = self.anahtar.sign(access_payload(iat=simdi - 300, exp=simdi - 20))
        self.assertEqual(self.error_code(self.access, token, leeway=0), "expired")

    def test_exp_zorunlu(self):
        token = self.anahtar.sign(access_payload(exp=None))
        self.assertEqual(self.error_code(self.access, token), "malformed")

    def test_not_yet_valid(self):
        simdi = int(time.time())
        token = self.anahtar.sign(access_payload(nbf=simdi + 120, exp=simdi + 600))
        self.assertEqual(self.error_code(self.access, token), "not_yet_valid")
        token = self.anahtar.sign(access_payload(iat=simdi + 120, exp=simdi + 600))
        self.assertEqual(self.error_code(self.access, token), "not_yet_valid")

    def test_unknown_key_id_refreshes_list_once(self):
        self.access(self.anahtar.sign(access_payload()))
        self.assertEqual(self.provider.call_count, 1)
        yeni = Anahtar("kid-2")
        self.provider.keys.append(yeni)
        self.assertEqual(self.access(yeni.sign(access_payload()))["azp"], "identity-sync")
        self.assertEqual(self.provider.call_count, 2)

    def test_kid_still_unknown_after_refresh(self):
        self.access(self.anahtar.sign(access_payload()))
        yabanci = Anahtar("kid-yok")
        self.assertEqual(self.error_code(self.access, yabanci.sign(access_payload())), "unknown_kid")
        self.assertEqual(self.provider.call_count, 2)
        # Art arda gelen bilinmeyen kid listeyi yeniden çektirmez.
        self.assertEqual(self.error_code(self.access, yabanci.sign(access_payload())), "unknown_kid")
        self.assertEqual(self.provider.call_count, 2)

    def test_cold_cache_unknown_kid_single_fetch(self):
        yabanci = Anahtar("kid-yok")
        self.assertEqual(self.error_code(self.access, yabanci.sign(access_payload())), "unknown_kid")
        self.assertEqual(self.provider.call_count, 1)

    def test_key_list_refreshes_after_expiration(self):
        time_now = [1000.0]
        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=self.provider, clock=lambda: time_now[0])
        self.access(self.anahtar.sign(access_payload()), cache=cache)
        self.access(self.anahtar.sign(access_payload()), cache=cache)
        self.assertEqual(self.provider.call_count, 1)
        time_now[0] += 601
        self.access(self.anahtar.sign(access_payload()), cache=cache)
        self.assertEqual(self.provider.call_count, 2)

    def test_error_message_excludes_token(self):
        token = self.anahtar.sign(access_payload(aud="press"))
        with self.assertRaises(TokenError) as caught:
            self.access(token)
        self.assertNotIn(token.split(".")[2], str(caught.exception))


class IdentityTokenTest(Temel):
    def identity(self, token, **ek):
        ayar = {"cache": self.cache, "issuer": ISSUER, "client_id": "press", "nonce": "n-123", "leeway": 30}
        ayar.update(ek)
        return verify_id_token(token, **ayar)

    def test_valid_identity_token(self):
        fields = self.identity(self.anahtar.sign(identity_payload()))
        self.assertEqual(fields["sid"], "s-123")
        self.assertEqual(fields["email"], "ayse.ornek@example.test")

    def test_wrong_nonce(self):
        token = self.anahtar.sign(identity_payload(nonce="baska"))
        self.assertEqual(self.error_code(self.identity, token), "wrong_nonce")
        token = self.anahtar.sign(identity_payload(nonce=None))
        self.assertEqual(self.error_code(self.identity, token), "wrong_nonce")

    def test_skips_nonce_validation_when_unset(self):
        # Çağıran nonce göndermediyse None verir. Belirteçteki nonce varlığı sonucu değiştirmez.
        fields = self.identity(self.anahtar.sign(identity_payload()), nonce=None)
        self.assertEqual(fields["nonce"], "n-123")
        fields = self.identity(self.anahtar.sign(identity_payload(nonce=None)), nonce=None)
        self.assertNotIn("nonce", fields)

    def test_wrong_aud_and_azp(self):
        token = self.anahtar.sign(identity_payload(aud="site-tenant1", azp="site-tenant1"))
        self.assertEqual(self.error_code(self.identity, token), "wrong_audience")
        token = self.anahtar.sign(identity_payload(azp="site-tenant1"))
        self.assertEqual(self.error_code(self.identity, token), "wrong_azp")

    def test_wrong_iss_and_lifetime(self):
        token = self.anahtar.sign(identity_payload(iss="https://kotu.example"))
        self.assertEqual(self.error_code(self.identity, token), "wrong_issuer")
        simdi = int(time.time())
        token = self.anahtar.sign(identity_payload(iat=simdi - 600, exp=simdi - 100))
        self.assertEqual(self.error_code(self.identity, token), "expired")


class LogoutTokenTest(Temel):
    def logout(self, token, **ek):
        ayar = {"cache": self.cache, "issuer": ISSUER, "client_id": "press", "leeway": 30}
        ayar.update(ek)
        return verify_logout_token(token, **ayar)

    def test_valid_logout_token(self):
        fields = self.logout(self.anahtar.sign(logout_payload()))
        self.assertEqual(fields["sid"], "s-123")
        self.assertIn(LOGOUT_EVENT, fields["events"])

    def test_valid_with_sub_only(self):
        fields = self.logout(self.anahtar.sign(logout_payload(sid=None)))
        self.assertEqual(fields["sub"], "f0d6f4d2-0000-4000-8000-000000000001")

    def test_logout_token_requires_events(self):
        token = self.anahtar.sign(logout_payload(events=None))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")
        token = self.anahtar.sign(logout_payload(events={"https://ornek.example/baska": {}}))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")

    def test_refused_without_sid_and_sub(self):
        token = self.anahtar.sign(logout_payload(sid=None, sub=None))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")

    def test_nonce_present_is_refused(self):
        token = self.anahtar.sign(logout_payload(nonce="n-1"))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")

    def test_iat_zorunlu_ve_gelecekte_olamaz(self):
        token = self.anahtar.sign(logout_payload(iat=None))
        self.assertEqual(self.error_code(self.logout, token), "malformed")
        token = self.anahtar.sign(logout_payload(iat=int(time.time()) + 300, exp=int(time.time()) + 600))
        self.assertEqual(self.error_code(self.logout, token), "not_yet_valid")

    def test_signature_iss_aud(self):
        baska = Anahtar("kid-1")
        self.assertEqual(self.error_code(self.logout, baska.sign(logout_payload())), "invalid_signature")
        self.assertEqual(
            self.error_code(self.logout, self.anahtar.sign(logout_payload(iss="https://kotu.example"))),
            "wrong_issuer",
        )
        self.assertEqual(
            self.error_code(self.logout, self.anahtar.sign(logout_payload(aud="site-tenant1"))),
            "wrong_audience",
        )


class JwksCacheTest(unittest.TestCase):
    def setUp(self):
        self.anahtar = Anahtar("kid-1")
        self.provider = FakeJwks(self.anahtar)
        self.time_now = [1000.0]
        self.cache = JwksCache(
            JWKS_URL,
            ttl_seconds=600,
            fetcher=self.provider,
            clock=lambda: self.time_now[0],
            min_refresh_seconds=5.0,
        )

    def access(self, token):
        return verify_access_token(
            token,
            cache=self.cache,
            issuer=ISSUER,
            audience="site-tenant1",
            allowed_azp={"identity-sync"},
            leeway=30,
        )

    def test_only_http_and_https_url(self):
        with self.assertRaises(ValueError):
            JwksCache("file:///etc/passwd")

    def test_default_lifetime_is_600_seconds(self):
        cache = JwksCache("https://identity.example/certs")
        self.assertEqual(cache.ttl_seconds, 600)

    def test_old_keys_used_when_refresh_fails(self):
        token = self.anahtar.sign(access_payload())
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        self.assertEqual(self.provider.call_count, 1)
        self.provider.error = URLError("bağlantı yok")
        self.time_now[0] += 601
        # Süre doldu. Çekim başarısız. Eski anahtar yine de doğrular.
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        self.assertEqual(self.provider.call_count, 2)
        # Aynı pencere içinde yeniden denenmez.
        self.time_now[0] += 2
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        self.assertEqual(self.provider.call_count, 2)
        # Pencere geçince bir kez daha denenir.
        self.time_now[0] += 4
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        self.assertEqual(self.provider.call_count, 3)
        # Sağlayıcı düzelince liste yenilenir ve yeni anahtar bulunur.
        self.provider.error = None
        yeni = Anahtar("kid-2")
        self.provider.keys.append(yeni)
        self.time_now[0] += 10
        self.assertEqual(self.access(yeni.sign(access_payload()))["azp"], "identity-sync")

    def test_preserves_old_key_for_invalid_json_and_payload(self):
        token = self.anahtar.sign(access_payload())
        self.access(token)
        for error in (ValueError("bozuk json"), OSError("yanıt 500"), TimeoutError()):
            self.provider.error = error
            self.time_now[0] += 601
            self.assertEqual(self.access(token)["azp"], "identity-sync")

    def test_failed_cold_cache_fetch_raises_jwks_unavailable(self):
        self.provider.error = URLError("bağlantı yok")
        token = self.anahtar.sign(access_payload())
        with self.assertRaises(JwksUnavailable):
            self.access(token)
        self.assertEqual(self.provider.call_count, 1)
        # Aynı pencere içinde sağlayıcı yeniden yorulmaz. Hata yine yükselir.
        self.time_now[0] += 1
        with self.assertRaises(JwksUnavailable):
            self.access(token)
        self.assertEqual(self.provider.call_count, 1)
        # Pencere geçince yeniden denenir ve sağlayıcı düzelmişse doğrulama geçer.
        self.provider.error = None
        self.time_now[0] += 5
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        self.assertEqual(self.provider.call_count, 2)

    def test_jwks_unavailable_token_error_degildir(self):
        self.assertFalse(issubclass(JwksUnavailable, TokenError))
        self.assertTrue(issubclass(JwksUnavailable, Exception))

    def test_broken_jwk_entry_is_skipped(self):
        self.provider.ham = [
            {"kty": "RSA", "kid": "kid-bozuk", "alg": "RS256", "use": "sig", "n": "!!!", "e": "AQAB"},
            {"kty": "RSA", "kid": "kid-eksik", "alg": "RS256", "use": "sig", "e": "AQAB"},
            {"kty": "RSA", "kid": "kid-tur", "alg": "RS256", "use": "sig", "n": 5, "e": "AQAB"},
            "dizi-degil",
        ]
        token = self.anahtar.sign(access_payload())
        self.assertEqual(self.access(token)["azp"], "identity-sync")
        yabanci = Anahtar("kid-bozuk")
        with self.assertRaises(TokenError) as caught:
            self.access(yabanci.sign(access_payload()))
        self.assertEqual(caught.exception.code, "unknown_kid")


class FrappeIndependenceTest(unittest.TestCase):
    def test_source_has_no_frappe(self):
        source_directory = Path(__file__).resolve().parent.parent / "src" / "oidc_verify"
        desen = re.compile(r"^\s*(import\s+frappe\b|from\s+frappe\b)")
        files = sorted(source_directory.glob("*.py"))
        self.assertTrue(files)
        for file in files:
            for numara, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(desen.match(line), f"{file.name}:{numara} frappe içe aktarıyor")


if __name__ == "__main__":
    unittest.main()
