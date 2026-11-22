"""Sihirli bağlantı ve Apple ile giriş eklentilerinin testleri (kontrol noktası 3).

Dosya testleri Keycloak gerektirmez. Canlı testler bin/kc-dev.sh test ile çalışır.
Beklenen değerler docs/kararlar/0003-keycloak-eklentileri.md notundan ve eklentilerin
belgelerinden alındı. Sihirli bağlantı kısa ömürlü ve tek kullanımlık olmalıdır.
"""

import base64
import json
import re
import time
import unittest
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar, DefaultCookiePolicy

from yardimci import KLASOR, ORNEK_ENV, admin, canli_var_mi, istek, jwt_govdesi, ortam, realm_oku, yonetici_belirteci

DOCKERFILE = KLASOR / "Dockerfile"
YER_TUTUCU = re.compile(r"^\$\{[A-Z0-9_]+\}$")
SIHIRLI = "skycloak-magic-link"
AKIS = "atonota-browser"
EN_UZUN_OMUR = 300


class EklentiDosyaTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    def test_eklenti_jarlari_sabit_surum_ve_ozetle_eklenir(self):
        self.assertIn("sky-cloak/keycloak-magic-link/releases/download/v0.3.0/", self.dockerfile)
        self.assertIn("klausbetz/apple-identity-provider-keycloak/releases/download/1.17.0/", self.dockerfile)
        self.assertEqual(self.dockerfile.count("--checksum=sha256:"), 2)

    def test_tarayici_akisi_sihirli_baglanti_tasir(self):
        self.assertEqual(self.realm["browserFlow"], AKIS)
        akislar = {a["alias"]: a for a in self.realm["authenticationFlows"]}
        self.assertIn(AKIS, akislar)
        yurutmeler = [y for a in akislar.values() for y in a["authenticationExecutions"]]
        sihirli = [y for y in yurutmeler if y.get("authenticator") == SIHIRLI]
        self.assertEqual(len(sihirli), 1)
        self.assertEqual(sihirli[0]["requirement"], "ALTERNATIVE")
        parola = [y for y in yurutmeler if y.get("authenticator") == "auth-username-password-form"]
        self.assertEqual(len(parola), 1, "parola yolu korunur")
        otp = [y for y in yurutmeler if y.get("authenticator") == "auth-otp-form"]
        self.assertEqual(otp[0]["requirement"], "ALTERNATIVE")

    def test_sihirli_baglanti_ayari_kisa_omur(self):
        ayarlar = {a["alias"]: a["config"] for a in self.realm["authenticatorConfig"]}
        sihirli = [y for a in self.realm["authenticationFlows"] for y in a["authenticationExecutions"] if y.get("authenticator") == SIHIRLI][0]
        ayar = ayarlar[sihirli["authenticatorConfig"]]
        self.assertLessEqual(int(ayar["token-lifespan-seconds"]), EN_UZUN_OMUR)
        self.assertEqual(ayar["auto-create-user"], "false")
        self.assertGreater(int(ayar["requests-per-minute-per-email"]), 0)
        self.assertGreater(int(ayar["requests-per-minute-per-ip"]), 0)

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


class Mailpit:
    def __init__(self, adres: str):
        self.adres = adres

    def temizle(self):
        istek("DELETE", f"{self.adres}/api/v1/messages")

    def son_baglanti(self, alici: str, sure: int = 20) -> str:
        bitis = time.time() + sure
        while time.time() < bitis:
            liste = istek("GET", f"{self.adres}/api/v1/messages").json().get("messages", [])
            for ileti in liste:
                if any(a.get("Address") == alici for a in ileti.get("To", [])):
                    ayrinti = istek("GET", f"{self.adres}/api/v1/message/{ileti['ID']}").json()
                    metin = (ayrinti.get("Text") or "") + " " + (ayrinti.get("HTML") or "")
                    bulunan = re.search(r"https?://[^\s\"'<>]+login-actions/action-token[^\s\"'<>]+", metin)
                    if bulunan:
                        return bulunan.group(0).replace("&amp;", "&")
            time.sleep(1)
        raise AssertionError(f"{alici} için sihirli bağlantı e-postası gelmedi")


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class EklentiCanliTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.yonetici = yonetici_belirteci()
        cls.mailpit = Mailpit(f"http://127.0.0.1:{ortam('MAILPIT_UI_PORT')}")

    def test_eklentiler_sunucuda_yuklu(self):
        bilgi = istek("GET", f"{self.kc}/admin/serverinfo", belirtec=self.yonetici).json()
        saglayicilar = bilgi["providers"]
        self.assertIn(SIHIRLI, saglayicilar["authenticator"]["providers"])
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
        self.assertEqual(saglayicilar[SIHIRLI]["requirement"], "ALTERNATIVE")
        self.assertEqual(saglayicilar["auth-username-password-form"]["requirement"], "REQUIRED")

    def test_tarayici_akisi_bagli_ve_apple_kapali(self):
        realm = admin("", self.yonetici).json()
        self.assertEqual(realm["browserFlow"], AKIS)
        apple = admin("/identity-provider/instances/apple", self.yonetici).json()
        self.assertFalse(apple["enabled"])
        self.assertEqual(apple["config"]["teamId"], ortam("ATONOTA_APPLE_TEAM_ID"))

    def _sihirli_baglanti_iste(self, eposta: str):
        """Giriş sayfasını açar, 'başka yol' ile sihirli bağlantıyı seçer, e-postayı gönderir."""
        acici = _cerezli_acici()
        sorgu = urllib.parse.urlencode(
            {
                "client_id": "site-kiraci1",
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": f"{ortam('ATONOTA_SITE_KIRACI1_URL')}/api/method/frappe.integrations.oauth2_logins.login_via_keycloak",
                "state": "test-state",
                "nonce": "test-nonce",
            }
        )
        durum, _, html = _ac(acici, f"{self.kc}/realms/platform/protocol/openid-connect/auth?{sorgu}")
        self.assertEqual(durum, 200)
        self.assertTrue("tryAnotherWay" in html, "giriş sayfasında başka yol bağlantısı olmalı")
        hedef = _form_hedefi(html)
        durum, _, html = _ac(acici, hedef, urllib.parse.urlencode({"tryAnotherWay": "on"}).encode())
        self.assertEqual(durum, 200)
        secim = re.search(r'name="authenticationExecution" value="([^"]+)"[^>]*>(?:(?!</button>).)*?Magic Link', html, re.S)
        if not secim:
            # Düğme metni çeviriye göre değişebilir. Yürütme kimliğini yönetici ucundan bul.
            yurutmeler = admin(f"/authentication/flows/{AKIS}/executions", self.yonetici).json()
            kimlik = [y["id"] for y in yurutmeler if y.get("providerId") == SIHIRLI][0]
        else:
            kimlik = secim.group(1)
        hedef = _form_hedefi(html)
        durum, _, html = _ac(acici, hedef, urllib.parse.urlencode({"authenticationExecution": kimlik}).encode())
        self.assertEqual(durum, 200)
        self.assertTrue('name="email"' in html, "sihirli bağlantı e-posta formu açılmalı")
        hedef = _form_hedefi(html)
        durum, _, html = _ac(acici, hedef, urllib.parse.urlencode({"email": eposta}).encode())
        self.assertEqual(durum, 200)
        return acici

    def test_sihirli_baglanti_kisa_omurlu_ve_tek_kullanimlik(self):
        eposta = "ayse.ornek@example.test"
        self.mailpit.temizle()
        acici = self._sihirli_baglanti_iste(eposta)
        baglanti = self.mailpit.son_baglanti(eposta)
        anahtar = urllib.parse.parse_qs(urllib.parse.urlsplit(baglanti).query)["key"][0]
        govde = jwt_govdesi(anahtar)
        self.assertLessEqual(govde["exp"] - govde["iat"], EN_UZUN_OMUR, "bağlantı ömrü kısa olmalı")
        # Aynı tarayıcıda ilk tıklama girişi tamamlar: Keycloak istemciye kod ile yönlendirir.
        durum, basliklar, _ = _keycloak_icinde_izle(acici, baglanti, self.kc)
        konum = basliklar.get("Location", "")
        self.assertEqual(durum, 302, "ilk kullanım istemciye yönlendirmeli")
        self.assertTrue(konum.startswith(ortam("ATONOTA_SITE_KIRACI1_URL")), konum[:120])
        self.assertIn("code=", konum)
        # İkinci tıklama aynı tarayıcıda bile kod vermez.
        durum2, basliklar2, _ = _keycloak_icinde_izle(acici, baglanti, self.kc)
        konum2 = basliklar2.get("Location", "")
        self.assertNotIn("code=", konum2, "bağlantı tek kullanımlıktır")

    def test_sihirli_baglanti_baska_tarayicida_calismaz(self):
        eposta = "mehmet.ornek@example.test"
        self.mailpit.temizle()
        self._sihirli_baglanti_iste(eposta)
        baglanti = self.mailpit.son_baglanti(eposta)
        yabanci = _cerezli_acici()
        durum, basliklar, _ = _keycloak_icinde_izle(yabanci, baglanti, self.kc)
        self.assertNotIn("code=", basliklar.get("Location", ""))
        self.assertIn(durum, (400, 403))


if __name__ == "__main__":
    unittest.main()
