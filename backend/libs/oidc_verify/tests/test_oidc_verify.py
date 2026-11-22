"""oidc_verify birim testleri. Beklenen davranış docs/sozlesmeler.md 3. bölümünden alındı.

Anahtarlar yerelde üretilir. Ağ yoktur. JwksCache sahte sağlayıcıyla beslenir.
"""

import re
import time
import unittest
from pathlib import Path
from urllib.error import URLError

from anahtarlar import ISSUER, LOGOUT_EVENT, Anahtar, SahteJwks, cikis_govdesi, erisim_govdesi, kimlik_govdesi

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
        self.saglayici = SahteJwks(self.anahtar)
        self.cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=self.saglayici)

    def erisim(self, token, **ek):
        ayar = {
            "cache": self.cache,
            "issuer": ISSUER,
            "audience": "site-kiraci1",
            "allowed_azp": {"identity-sync"},
            "leeway": 30,
        }
        ayar.update(ek)
        return verify_access_token(token, **ayar)

    def hata_kodu(self, islev, *args, **kwargs) -> str:
        with self.assertRaises(TokenError) as yakalanan:
            islev(*args, **kwargs)
        return yakalanan.exception.code


class ErisimBelirteciTesti(Temel):
    def test_dogru_belirtec_alanlari_doner(self):
        token = self.anahtar.imzala(erisim_govdesi())
        alanlar = self.erisim(token)
        self.assertEqual(alanlar["sub"], "service-account-identity-sync")
        self.assertEqual(alanlar["aud"], "site-kiraci1")
        self.assertEqual(alanlar["azp"], "identity-sync")

    def test_tek_elemanli_aud_listesi_kabul(self):
        token = self.anahtar.imzala(erisim_govdesi(aud=["site-kiraci1"]))
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")

    def test_yanlis_imza(self):
        baska = Anahtar("kid-1")
        token = baska.imzala(erisim_govdesi())
        self.assertEqual(self.hata_kodu(self.erisim, token), "invalid_signature")

    def test_none_algoritmasi(self):
        token = self.anahtar.imzala(erisim_govdesi(), alg="none")
        self.assertEqual(self.hata_kodu(self.erisim, token), "invalid_signature")

    def test_rs256_disi_algoritma(self):
        token = self.anahtar.imzala(erisim_govdesi(), alg="RS512")
        self.assertEqual(self.hata_kodu(self.erisim, token), "invalid_signature")

    def test_bozuk_belirtec(self):
        self.assertEqual(self.hata_kodu(self.erisim, "abc.def"), "malformed")
        self.assertEqual(self.hata_kodu(self.erisim, ""), "malformed")
        self.assertEqual(self.hata_kodu(self.erisim, "a.b.c"), "malformed")

    def test_kid_yoksa_bozuk(self):
        import jwt

        token = jwt.encode(erisim_govdesi(), self.anahtar.ozel_pem, algorithm="RS256")
        self.assertEqual(self.hata_kodu(self.erisim, token), "malformed")

    def test_yanlis_iss(self):
        token = self.anahtar.imzala(erisim_govdesi(iss=ISSUER + "x"))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_issuer")
        token = self.anahtar.imzala(erisim_govdesi(iss=None))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_issuer")

    def test_yanlis_aud(self):
        token = self.anahtar.imzala(erisim_govdesi(aud="press"))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_audience")
        token = self.anahtar.imzala(erisim_govdesi(aud=None))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_audience")

    def test_birden_cok_aud_reddedilir(self):
        token = self.anahtar.imzala(erisim_govdesi(aud=["site-kiraci1", "account"]))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_audience")

    def test_yanlis_azp(self):
        token = self.anahtar.imzala(erisim_govdesi(azp="press-service"))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_azp")
        token = self.anahtar.imzala(erisim_govdesi(azp=None))
        self.assertEqual(self.hata_kodu(self.erisim, token), "wrong_azp")

    def test_izinli_azp_kumesinden_biri(self):
        token = self.anahtar.imzala(erisim_govdesi(azp="press-service"))
        alanlar = self.erisim(token, allowed_azp={"identity-sync", "press-service"})
        self.assertEqual(alanlar["azp"], "press-service")

    def test_suresi_dolmus(self):
        simdi = int(time.time())
        token = self.anahtar.imzala(erisim_govdesi(iat=simdi - 400, exp=simdi - 60))
        self.assertEqual(self.hata_kodu(self.erisim, token), "expired")

    def test_30_saniyelik_pay_icinde_gecerli(self):
        simdi = int(time.time())
        token = self.anahtar.imzala(erisim_govdesi(iat=simdi - 300, exp=simdi - 20))
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        token = self.anahtar.imzala(erisim_govdesi(iat=simdi - 300, exp=simdi - 40))
        self.assertEqual(self.hata_kodu(self.erisim, token), "expired")

    def test_pay_sifirken_dolmus_sayilir(self):
        simdi = int(time.time())
        token = self.anahtar.imzala(erisim_govdesi(iat=simdi - 300, exp=simdi - 20))
        self.assertEqual(self.hata_kodu(self.erisim, token, leeway=0), "expired")

    def test_exp_zorunlu(self):
        token = self.anahtar.imzala(erisim_govdesi(exp=None))
        self.assertEqual(self.hata_kodu(self.erisim, token), "malformed")

    def test_henuz_gecerli_degil(self):
        simdi = int(time.time())
        token = self.anahtar.imzala(erisim_govdesi(nbf=simdi + 120, exp=simdi + 600))
        self.assertEqual(self.hata_kodu(self.erisim, token), "not_yet_valid")
        token = self.anahtar.imzala(erisim_govdesi(iat=simdi + 120, exp=simdi + 600))
        self.assertEqual(self.hata_kodu(self.erisim, token), "not_yet_valid")

    def test_bilinmeyen_kid_listeyi_bir_kez_yeniler(self):
        self.erisim(self.anahtar.imzala(erisim_govdesi()))
        self.assertEqual(self.saglayici.cagri, 1)
        yeni = Anahtar("kid-2")
        self.saglayici.anahtarlar.append(yeni)
        self.assertEqual(self.erisim(yeni.imzala(erisim_govdesi()))["azp"], "identity-sync")
        self.assertEqual(self.saglayici.cagri, 2)

    def test_yenilemeden_sonra_da_bilinmeyen_kid(self):
        self.erisim(self.anahtar.imzala(erisim_govdesi()))
        yabanci = Anahtar("kid-yok")
        self.assertEqual(self.hata_kodu(self.erisim, yabanci.imzala(erisim_govdesi())), "unknown_kid")
        self.assertEqual(self.saglayici.cagri, 2)
        # Art arda gelen bilinmeyen kid listeyi yeniden çektirmez.
        self.assertEqual(self.hata_kodu(self.erisim, yabanci.imzala(erisim_govdesi())), "unknown_kid")
        self.assertEqual(self.saglayici.cagri, 2)

    def test_soguk_onbellekte_bilinmeyen_kid_tek_cekim(self):
        yabanci = Anahtar("kid-yok")
        self.assertEqual(self.hata_kodu(self.erisim, yabanci.imzala(erisim_govdesi())), "unknown_kid")
        self.assertEqual(self.saglayici.cagri, 1)

    def test_liste_ttl_dolunca_yenilenir(self):
        zaman = [1000.0]
        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=self.saglayici, clock=lambda: zaman[0])
        self.erisim(self.anahtar.imzala(erisim_govdesi()), cache=cache)
        self.erisim(self.anahtar.imzala(erisim_govdesi()), cache=cache)
        self.assertEqual(self.saglayici.cagri, 1)
        zaman[0] += 601
        self.erisim(self.anahtar.imzala(erisim_govdesi()), cache=cache)
        self.assertEqual(self.saglayici.cagri, 2)

    def test_hata_mesaji_belirteci_icermez(self):
        token = self.anahtar.imzala(erisim_govdesi(aud="press"))
        with self.assertRaises(TokenError) as yakalanan:
            self.erisim(token)
        self.assertNotIn(token.split(".")[2], str(yakalanan.exception))


class KimlikBelirteciTesti(Temel):
    def kimlik(self, token, **ek):
        ayar = {"cache": self.cache, "issuer": ISSUER, "client_id": "press", "nonce": "n-123", "leeway": 30}
        ayar.update(ek)
        return verify_id_token(token, **ayar)

    def test_dogru_kimlik_belirteci(self):
        alanlar = self.kimlik(self.anahtar.imzala(kimlik_govdesi()))
        self.assertEqual(alanlar["sid"], "s-123")
        self.assertEqual(alanlar["email"], "ayse.ornek@example.test")

    def test_yanlis_nonce(self):
        token = self.anahtar.imzala(kimlik_govdesi(nonce="baska"))
        self.assertEqual(self.hata_kodu(self.kimlik, token), "wrong_nonce")
        token = self.anahtar.imzala(kimlik_govdesi(nonce=None))
        self.assertEqual(self.hata_kodu(self.kimlik, token), "wrong_nonce")

    def test_nonce_none_denetimi_atlar(self):
        # Çağıran nonce göndermediyse None verir. Belirteçteki nonce varlığı sonucu değiştirmez.
        alanlar = self.kimlik(self.anahtar.imzala(kimlik_govdesi()), nonce=None)
        self.assertEqual(alanlar["nonce"], "n-123")
        alanlar = self.kimlik(self.anahtar.imzala(kimlik_govdesi(nonce=None)), nonce=None)
        self.assertNotIn("nonce", alanlar)

    def test_yanlis_aud_ve_azp(self):
        token = self.anahtar.imzala(kimlik_govdesi(aud="site-kiraci1", azp="site-kiraci1"))
        self.assertEqual(self.hata_kodu(self.kimlik, token), "wrong_audience")
        token = self.anahtar.imzala(kimlik_govdesi(azp="site-kiraci1"))
        self.assertEqual(self.hata_kodu(self.kimlik, token), "wrong_azp")

    def test_yanlis_iss_ve_sure(self):
        token = self.anahtar.imzala(kimlik_govdesi(iss="https://kotu.example"))
        self.assertEqual(self.hata_kodu(self.kimlik, token), "wrong_issuer")
        simdi = int(time.time())
        token = self.anahtar.imzala(kimlik_govdesi(iat=simdi - 600, exp=simdi - 100))
        self.assertEqual(self.hata_kodu(self.kimlik, token), "expired")


class CikisBelirteciTesti(Temel):
    def cikis(self, token, **ek):
        ayar = {"cache": self.cache, "issuer": ISSUER, "client_id": "press", "leeway": 30}
        ayar.update(ek)
        return verify_logout_token(token, **ayar)

    def test_gecerli_cikis_belirteci(self):
        alanlar = self.cikis(self.anahtar.imzala(cikis_govdesi()))
        self.assertEqual(alanlar["sid"], "s-123")
        self.assertIn(LOGOUT_EVENT, alanlar["events"])

    def test_yalniz_sub_ile_gecerli(self):
        alanlar = self.cikis(self.anahtar.imzala(cikis_govdesi(sid=None)))
        self.assertEqual(alanlar["sub"], "f0d6f4d2-0000-4000-8000-000000000001")

    def test_events_yoksa_cikis_belirteci_degil(self):
        token = self.anahtar.imzala(cikis_govdesi(events=None))
        self.assertEqual(self.hata_kodu(self.cikis, token), "not_logout_token")
        token = self.anahtar.imzala(cikis_govdesi(events={"https://ornek.example/baska": {}}))
        self.assertEqual(self.hata_kodu(self.cikis, token), "not_logout_token")

    def test_sid_ve_sub_yoksa_reddedilir(self):
        token = self.anahtar.imzala(cikis_govdesi(sid=None, sub=None))
        self.assertEqual(self.hata_kodu(self.cikis, token), "not_logout_token")

    def test_nonce_varsa_reddedilir(self):
        token = self.anahtar.imzala(cikis_govdesi(nonce="n-1"))
        self.assertEqual(self.hata_kodu(self.cikis, token), "not_logout_token")

    def test_iat_zorunlu_ve_gelecekte_olamaz(self):
        token = self.anahtar.imzala(cikis_govdesi(iat=None))
        self.assertEqual(self.hata_kodu(self.cikis, token), "malformed")
        token = self.anahtar.imzala(cikis_govdesi(iat=int(time.time()) + 300, exp=int(time.time()) + 600))
        self.assertEqual(self.hata_kodu(self.cikis, token), "not_yet_valid")

    def test_imza_iss_aud(self):
        baska = Anahtar("kid-1")
        self.assertEqual(self.hata_kodu(self.cikis, baska.imzala(cikis_govdesi())), "invalid_signature")
        self.assertEqual(
            self.hata_kodu(self.cikis, self.anahtar.imzala(cikis_govdesi(iss="https://kotu.example"))),
            "wrong_issuer",
        )
        self.assertEqual(
            self.hata_kodu(self.cikis, self.anahtar.imzala(cikis_govdesi(aud="site-kiraci1"))),
            "wrong_audience",
        )


class JwksCacheTesti(unittest.TestCase):
    def setUp(self):
        self.anahtar = Anahtar("kid-1")
        self.saglayici = SahteJwks(self.anahtar)
        self.zaman = [1000.0]
        self.cache = JwksCache(
            JWKS_URL,
            ttl_seconds=600,
            fetcher=self.saglayici,
            clock=lambda: self.zaman[0],
            min_refresh_seconds=5.0,
        )

    def erisim(self, token):
        return verify_access_token(
            token,
            cache=self.cache,
            issuer=ISSUER,
            audience="site-kiraci1",
            allowed_azp={"identity-sync"},
            leeway=30,
        )

    def test_yalniz_http_ve_https_adresi(self):
        with self.assertRaises(ValueError):
            JwksCache("file:///etc/passwd")

    def test_varsayilan_sure_600(self):
        cache = JwksCache("https://kimlik.example/certs")
        self.assertEqual(cache.ttl_seconds, 600)

    def test_yenileme_basarisizsa_eski_anahtarlar_kullanilir(self):
        token = self.anahtar.imzala(erisim_govdesi())
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        self.assertEqual(self.saglayici.cagri, 1)
        self.saglayici.hata = URLError("bağlantı yok")
        self.zaman[0] += 601
        # Süre doldu. Çekim başarısız. Eski anahtar yine de doğrular.
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        self.assertEqual(self.saglayici.cagri, 2)
        # Aynı pencere içinde yeniden denenmez.
        self.zaman[0] += 2
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        self.assertEqual(self.saglayici.cagri, 2)
        # Pencere geçince bir kez daha denenir.
        self.zaman[0] += 4
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        self.assertEqual(self.saglayici.cagri, 3)
        # Sağlayıcı düzelince liste yenilenir ve yeni anahtar bulunur.
        self.saglayici.hata = None
        yeni = Anahtar("kid-2")
        self.saglayici.anahtarlar.append(yeni)
        self.zaman[0] += 10
        self.assertEqual(self.erisim(yeni.imzala(erisim_govdesi()))["azp"], "identity-sync")

    def test_bozuk_json_ve_bozuk_govde_de_eski_anahtari_korur(self):
        token = self.anahtar.imzala(erisim_govdesi())
        self.erisim(token)
        for hata in (ValueError("bozuk json"), OSError("yanıt 500"), TimeoutError()):
            self.saglayici.hata = hata
            self.zaman[0] += 601
            self.assertEqual(self.erisim(token)["azp"], "identity-sync")

    def test_soguk_onbellekte_cekim_basarisizsa_jwks_unavailable(self):
        self.saglayici.hata = URLError("bağlantı yok")
        token = self.anahtar.imzala(erisim_govdesi())
        with self.assertRaises(JwksUnavailable):
            self.erisim(token)
        self.assertEqual(self.saglayici.cagri, 1)
        # Aynı pencere içinde sağlayıcı yeniden yorulmaz. Hata yine yükselir.
        self.zaman[0] += 1
        with self.assertRaises(JwksUnavailable):
            self.erisim(token)
        self.assertEqual(self.saglayici.cagri, 1)
        # Pencere geçince yeniden denenir ve sağlayıcı düzelmişse doğrulama geçer.
        self.saglayici.hata = None
        self.zaman[0] += 5
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        self.assertEqual(self.saglayici.cagri, 2)

    def test_jwks_unavailable_token_error_degildir(self):
        self.assertFalse(issubclass(JwksUnavailable, TokenError))
        self.assertTrue(issubclass(JwksUnavailable, Exception))

    def test_bozuk_jwk_kaydi_atlanir(self):
        self.saglayici.ham = [
            {"kty": "RSA", "kid": "kid-bozuk", "alg": "RS256", "use": "sig", "n": "!!!", "e": "AQAB"},
            {"kty": "RSA", "kid": "kid-eksik", "alg": "RS256", "use": "sig", "e": "AQAB"},
            {"kty": "RSA", "kid": "kid-tur", "alg": "RS256", "use": "sig", "n": 5, "e": "AQAB"},
            "dizi-degil",
        ]
        token = self.anahtar.imzala(erisim_govdesi())
        self.assertEqual(self.erisim(token)["azp"], "identity-sync")
        yabanci = Anahtar("kid-bozuk")
        with self.assertRaises(TokenError) as yakalanan:
            self.erisim(yabanci.imzala(erisim_govdesi()))
        self.assertEqual(yakalanan.exception.code, "unknown_kid")


class FrappeBagimsizligiTesti(unittest.TestCase):
    def test_kaynak_frappe_icermez(self):
        kaynak = Path(__file__).resolve().parent.parent / "src" / "oidc_verify"
        desen = re.compile(r"^\s*(import\s+frappe\b|from\s+frappe\b)")
        dosyalar = sorted(kaynak.glob("*.py"))
        self.assertTrue(dosyalar)
        for dosya in dosyalar:
            for numara, satir in enumerate(dosya.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(desen.match(satir), f"{dosya.name}:{numara} frappe içe aktarıyor")


if __name__ == "__main__":
    unittest.main()
