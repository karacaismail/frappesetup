"""Sihirli bağlantı ve Apple ile giriş eklentilerinin testleri (kontrol noktası 3).

Dosya testleri Keycloak gerektirmez. Canlı testler bin/kc-dev.sh test ile çalışır.
Beklenen değerler docs/kararlar/0003-keycloak-eklentileri.md notundan ve eklentilerin
belgelerinden alındı. Sihirli bağlantı kısa ömürlü ve tek kullanımlık olmalıdır.
"""

import re
import unittest
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar, DefaultCookiePolicy

from yardimci import KLASOR, ORNEK_ENV, admin, canli_var_mi, istek, istemci_belirteci, ortam, realm_oku, yonetici_belirteci

DOCKERFILE = KLASOR / "Dockerfile"
YER_TUTUCU = re.compile(r"^\$\{[A-Z0-9_]+\}$")
SIHIRLI = "skycloak-magic-link"
AKIS = "atonota-browser"
POST_BROKER = "atonota-post-broker"


class EklentiDosyaTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    def test_eklenti_jarlari_sabit_surum_ve_ozetle_eklenir(self):
        # The magic link extension is out of the MVP (second review, E1 and E2). Only Apple remains.
        self.assertNotIn("keycloak-magic-link", self.dockerfile)
        self.assertIn("klausbetz/apple-identity-provider-keycloak/releases/download/1.17.0/", self.dockerfile)
        self.assertEqual(self.dockerfile.count("--checksum=sha256:"), 1)

    def test_tarayici_akisinda_sihirli_baglanti_yok(self):
        self.assertEqual(self.realm["browserFlow"], AKIS)
        yurutmeler = [y for a in self.realm["authenticationFlows"] for y in a["authenticationExecutions"]]
        self.assertEqual([y for y in yurutmeler if y.get("authenticator") == SIHIRLI], [])
        self.assertNotIn("atonota-sihirli-baglanti", {a["alias"] for a in self.realm["authenticatorConfig"]})
        parola = [y for y in yurutmeler if y.get("authenticator") == "auth-username-password-form"]
        self.assertEqual(len(parola), 1, "password path stays")
        otp = [y for y in yurutmeler if y.get("authenticator") == "auth-otp-form"]
        self.assertTrue(otp and all(o["requirement"] == "ALTERNATIVE" for o in otp))

    def test_social_providers_have_post_broker_second_factor(self):
        # O6: after a social login the second factor must be asked when the user has one.
        akislar = {a["alias"]: a for a in self.realm["authenticationFlows"]}
        for alias in ("google", "apple"):
            idp = [s for s in self.realm["identityProviders"] if s["alias"] == alias][0]
            self.assertEqual(idp.get("postBrokerLoginFlowAlias"), POST_BROKER, alias)
        self.assertIn(POST_BROKER, akislar)
        alt = [y.get("flowAlias") for y in akislar[POST_BROKER]["authenticationExecutions"] if y.get("authenticatorFlow")]
        yurutmeler = [y for a in [akislar[POST_BROKER]] + [akislar[x] for x in alt] for y in a["authenticationExecutions"]]
        self.assertIn("conditional-user-configured", [y.get("authenticator") for y in yurutmeler])
        self.assertIn("auth-otp-form", [y.get("authenticator") for y in yurutmeler])

    def test_apple_saglayicisi_kapali_ve_anahtarsiz(self):
        apple = [s for s in self.realm["identityProviders"] if s["alias"] == "apple"]
        self.assertEqual(len(apple), 1)
        self.assertEqual(apple[0]["providerId"], "apple")
        self.assertFalse(apple[0]["enabled"])
        for anahtar in ("clientId", "clientSecret", "teamId", "keyId"):
            self.assertRegex(apple[0]["config"][anahtar], YER_TUTUCU, anahtar)
        env_anahtarlari = set(re.findall(r"^([A-Z0-9_]+)=", ORNEK_ENV.read_text(encoding="utf-8"), re.M))
        for anahtar in ("clientId", "clientSecret", "teamId", "keyId"):
            self.assertIn(apple[0]["config"][anahtar][2:-1], env_anahtarlari)


def _cerezli_acici() -> urllib.request.OpenerDirector:
    class Yonlendirme(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # yönlendirmeyi izleme, Location başlığını oku

    # Keycloak çerezleri Secure bayrağıyla verir. Tarayıcılar *.localhost adresini güvenli sayar ve
    # çerezi http üzerinden de gönderir. Python'un kavanozu aynı davranışı bu ayarla verir.
    kavanoz = CookieJar(DefaultCookiePolicy(secure_protocols=("https", "wss", "http")))
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(kavanoz), Yonlendirme())


def _ac(acici, adres, veri=None):
    """Yanıtı (durum, başlıklar, gövde) olarak döner. Yönlendirme izlenmez."""
    try:
        with acici.open(urllib.request.Request(adres, data=veri), timeout=30) as yanit:
            return yanit.status, dict(yanit.headers), yanit.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as hata:
        return hata.code, dict(hata.headers), hata.read().decode("utf-8", "replace")


def _keycloak_icinde_izle(acici, adres: str, kc: str):
    """Keycloak içindeki yönlendirmeleri izler. Keycloak dışına çıkan ilk adreste durur."""
    durum, basliklar, govde = _ac(acici, adres)
    for _ in range(5):
        konum = basliklar.get("Location", "")
        if durum not in (301, 302, 303) or not konum.startswith(kc):
            break
        durum, basliklar, govde = _ac(acici, konum)
    return durum, basliklar, govde


def _form_hedefi(html: str) -> str:
    eslesme = re.search(r'action="([^"]*login-actions/authenticate[^"]*)"', html)
    if not eslesme:
        raise AssertionError("giriş formu bulunamadı")
    return eslesme.group(1).replace("&amp;", "&")


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class EklentiCanliTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.yonetici = yonetici_belirteci()

    def test_eklentiler_sunucuda_yuklu(self):
        bilgi = istek("GET", f"{self.kc}/admin/serverinfo", belirtec=self.yonetici).json()
        saglayicilar = bilgi["providers"]
        self.assertIn("apple", saglayicilar["social"]["providers"])
        # Passkey özelliği sunucuda açık olmalı. Yoksa realm'deki passkey ayarı etkisizdir.
        ozellikler = {o["name"]: o for o in bilgi.get("features", [])}
        self.assertIn("PASSKEYS", ozellikler, sorted(ozellikler))
        self.assertTrue(ozellikler["PASSKEYS"]["enabled"])

    def test_tarayici_akisinda_passkey_kosulu_ve_otp_var(self):
        yurutmeler = admin(f"/authentication/flows/{AKIS}/executions", self.yonetici).json()
        saglayicilar = {y.get("providerId"): y for y in yurutmeler}
        self.assertEqual(saglayicilar["auth-otp-form"]["requirement"], "ALTERNATIVE")
        self.assertEqual(saglayicilar["conditional-credential"]["requirement"], "REQUIRED")
        self.assertEqual(saglayicilar["webauthn-authenticator"]["requirement"], "ALTERNATIVE")
        self.assertNotIn(SIHIRLI, saglayicilar)
        self.assertEqual(saglayicilar["auth-username-password-form"]["requirement"], "REQUIRED")

    def test_tarayici_akisi_bagli_ve_apple_kapali(self):
        realm = admin("", self.yonetici).json()
        self.assertEqual(realm["browserFlow"], AKIS)
        apple = admin("/identity-provider/instances/apple", self.yonetici).json()
        self.assertFalse(apple["enabled"])
        self.assertEqual(apple["config"]["teamId"], ortam("ATONOTA_APPLE_TEAM_ID"))

    def test_magic_link_endpoints_are_gone(self):
        # Acceptance for removing the extension: its realm resource no longer exists.
        saglik = istek("GET", f"{self.kc}/realms/platform/skycloak-magic-link/health")
        self.assertEqual(saglik.durum, 404)
        yanit = istemci_belirteci("identity-sync", ortam("ATONOTA_IDENTITY_SYNC_SECRET"), "admin-api kc-admin-api")
        self.assertEqual(yanit.durum, 200)
        uretim = istek(
            "POST",
            f"{self.kc}/realms/platform/skycloak-magic-link",
            govde={"email": "ayse.ornek@example.test", "clientId": "site-kiraci1", "redirectUri": "https://x.example", "send": False},
            belirtec=yanit.json()["access_token"],
        )
        self.assertEqual(uretim.durum, 404)
        bilgi = istek("GET", f"{self.kc}/admin/serverinfo", belirtec=self.yonetici).json()["providers"]
        self.assertNotIn(SIHIRLI, bilgi["authenticator"]["providers"])

    def test_post_broker_flow_is_bound_to_social_providers(self):
        for alias in ("google", "apple"):
            idp = admin(f"/identity-provider/instances/{alias}", self.yonetici).json()
            self.assertEqual(idp.get("postBrokerLoginFlowAlias"), POST_BROKER, alias)
        yurutmeler = admin(f"/authentication/flows/{POST_BROKER}/executions", self.yonetici).json()
        saglayicilar = {y.get("providerId"): y for y in yurutmeler}
        self.assertIn("conditional-user-configured", saglayicilar)
        self.assertEqual(saglayicilar["auth-otp-form"]["requirement"], "ALTERNATIVE")


if __name__ == "__main__":
    unittest.main()
