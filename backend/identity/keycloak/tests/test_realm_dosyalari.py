"""Realm dosyalarının depo kurallarını sınar. Keycloak gerekmez.

Beklenen değerler docs/sozlesmeler.md 2. bölümünden ve görev belgesinden alındı.
"""

import re
import unittest

from yardimci import KLASOR, KULLANICI_DOSYASI, ORNEK_ENV, PAROLA_LISTESI, REALM_DOSYASI, kullanicilari_oku, realm_oku

YER_TUTUCU = re.compile(r"^\$\{[A-Z0-9_]+\}$")
ISTEMCILER = {"site-kiraci1", "press", "identity-sync", "press-service"}
HEDEF_KAPSAMLARI = {"aud-site-kiraci1": "site-kiraci1", "aud-press": "press"}


class RealmDosyasiTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.istemciler = {i["clientId"]: i for i in cls.realm.get("clients", [])}
        cls.kapsamlar = {k["name"]: k for k in cls.realm.get("clientScopes", [])}

    def test_dosya_adi_realm_adiyla_ayni(self):
        # Keycloak dizin içe alımı <realm>-realm.json adını ister (DirImportProvider.java:138).
        self.assertEqual(self.realm["realm"], "platform")
        self.assertEqual(REALM_DOSYASI.name, "platform-realm.json")

    def test_gorunen_ad_ve_diller(self):
        # D-4: the brand name comes from a variable. The development value is "Atonota" (test_realm_backlog).
        self.assertEqual(self.realm["displayName"], "${IDENTITY_BRAND_NAME}")
        self.assertTrue(self.realm["internationalizationEnabled"])
        self.assertEqual(self.realm["defaultLocale"], "tr")
        self.assertEqual(set(self.realm["supportedLocales"]), {"tr", "en"})

    def test_giris_ve_eposta_temasi_atonota(self):
        # Sözleşme 2. bölüm: giriş ve e-posta teması atonota adını taşır. Tema kimlik-tema işinden gelir.
        self.assertEqual(self.realm["loginTheme"], "atonota")
        self.assertEqual(self.realm["emailTheme"], "atonota")

    def test_istemciler_var(self):
        self.assertTrue(ISTEMCILER <= set(self.istemciler), set(self.istemciler))

    def test_hedef_kapsamlari_tek_aud_ekler(self):
        for ad, hedef in HEDEF_KAPSAMLARI.items():
            kapsam = self.kapsamlar[ad]
            eslesticiler = [m for m in kapsam["protocolMappers"] if m["protocolMapper"] == "oidc-audience-mapper"]
            self.assertEqual(len(eslesticiler), 1, ad)
            self.assertEqual(eslesticiler[0]["config"]["included.client.audience"], hedef)
            self.assertEqual(eslesticiler[0]["config"]["access.token.claim"], "true")

    def test_hedef_kapsamlari_varsayilan_degil(self):
        for istemci in self.istemciler.values():
            for ad in HEDEF_KAPSAMLARI:
                self.assertNotIn(ad, istemci.get("defaultClientScopes", []), istemci["clientId"])

    def test_servis_istemcileri_kapsamlarini_sozlesmeye_gore_alir(self):
        self.assertIn("aud-site-kiraci1", self.istemciler["identity-sync"]["optionalClientScopes"])
        self.assertIn("aud-press", self.istemciler["identity-sync"]["optionalClientScopes"])
        self.assertIn("aud-site-kiraci1", self.istemciler["press-service"]["optionalClientScopes"])
        self.assertNotIn("aud-press", self.istemciler["press-service"]["optionalClientScopes"])

    def test_servis_istemcileri_tam_kapsam_tasimaz(self):
        # Tam kapsam açık olsaydı hesap rolleri belirtece girer ve aud ikinci değer alırdı.
        for ad in ("identity-sync", "press-service"):
            self.assertTrue(self.istemciler[ad]["serviceAccountsEnabled"], ad)
            self.assertFalse(self.istemciler[ad]["standardFlowEnabled"], ad)
            self.assertFalse(self.istemciler[ad]["fullScopeAllowed"], ad)

    def test_tarayici_istemcileri_kod_akisi_ve_tam_donus_adresi(self):
        for ad in ("site-kiraci1", "press"):
            istemci = self.istemciler[ad]
            self.assertTrue(istemci["standardFlowEnabled"], ad)
            self.assertFalse(istemci["implicitFlowEnabled"], ad)
            self.assertFalse(istemci["directAccessGrantsEnabled"], ad)
            self.assertFalse(istemci["publicClient"], ad)
            for adres in istemci["redirectUris"]:
                self.assertNotIn("*", adres, ad)
            self.assertEqual(istemci["attributes"]["backchannel.logout.session.required"], "true", ad)
            self.assertIn("backchannel.logout.url", istemci["attributes"], ad)

    def test_tenant_client_callback_and_pkce(self):
        # Contract section 2 (66d9ad8): the tenant client returns to platform_core.api.auth.keycloak_callback
        # and requires PKCE with S256.
        istemci = self.istemciler["site-kiraci1"]
        self.assertEqual(istemci["redirectUris"], ["${ATONOTA_SITE_KIRACI1_URL}/api/method/platform_core.api.auth.keycloak_callback"])
        self.assertEqual(istemci["attributes"]["pkce.code.challenge.method"], "S256")

    def test_istemci_sirlari_yer_tutucu(self):
        for istemci in self.istemciler.values():
            if istemci["publicClient"]:
                continue
            self.assertRegex(istemci["secret"], YER_TUTUCU, istemci["clientId"])

    def test_google_saglayicisi_kapali_ve_anahtarsiz(self):
        google = [s for s in self.realm["identityProviders"] if s["alias"] == "google"]
        self.assertEqual(len(google), 1)
        self.assertFalse(google[0]["enabled"])
        self.assertRegex(google[0]["config"]["clientId"], YER_TUTUCU)
        self.assertRegex(google[0]["config"]["clientSecret"], YER_TUTUCU)

    def test_politikalar_g78(self):
        r = self.realm
        self.assertTrue(r["loginWithEmailAllowed"])
        self.assertTrue(r["verifyEmail"])
        self.assertTrue(r["bruteForceProtected"])
        self.assertEqual(r["failureFactor"], 5)
        self.assertEqual(r["maxDeltaTimeSeconds"], 300)
        self.assertIn("length(12)", r["passwordPolicy"])
        self.assertIn("passwordHistory(", r["passwordPolicy"])
        self.assertIn("passwordBlacklist(yaygin-parolalar.txt)", r["passwordPolicy"])
        # O-25 replaced the G-78 web lifetimes: the realm carries the customer values (7 days, 30 days).
        # Employee clients have 1 hour and 24 hours (test_session_lifetimes).
        self.assertEqual(r["ssoSessionIdleTimeout"], 7 * 24 * 60 * 60)
        self.assertEqual(r["ssoSessionMaxLifespan"], 30 * 24 * 60 * 60)
        self.assertEqual(r["accessTokenLifespan"], 5 * 60)
        self.assertTrue(r["revokeRefreshToken"])
        self.assertEqual(r["refreshTokenMaxReuse"], 0)
        self.assertFalse(r["rememberMe"])

    def test_imza_algoritmasi_rs256(self):
        # Sözleşme 3. bölüm: kitaplık yalnız RS256 kabul eder. Realm de RS256 ile imzalar.
        self.assertEqual(self.realm["defaultSignatureAlgorithm"], "RS256")

    def test_totp_ve_passkey(self):
        self.assertEqual(self.realm["otpPolicyType"], "totp")
        self.assertTrue(self.realm["webAuthnPolicyPasswordlessPasskeysEnabled"])
        self.assertEqual(self.realm["webAuthnPolicyPasswordlessRpEntityName"], "Atonota")

    def test_realm_dosyasinda_kisi_yok(self):
        for kullanici in self.realm.get("users", []):
            self.assertIn("serviceAccountClientId", kullanici, kullanici.get("username"))
            self.assertNotIn("email", kullanici)
            self.assertNotIn("credentials", kullanici)

    def test_identity_sync_has_least_privilege(self):
        # Contract 26a274c: identity-sync writes users (invites) and organizations (membership).
        # Minimum set verified in Keycloak 26.8.2 (docs/kararlar/0003-keycloak-eklentileri.md).
        beklenen = {"view-users", "query-users", "manage-users", "view-organizations", "manage-organizations"}
        eslemeler = self.realm["clientScopeMappings"]["realm-management"]
        self.assertEqual(set(eslemeler[0]["roles"]), beklenen)
        hesap = [u for u in self.realm["users"] if u.get("serviceAccountClientId") == "identity-sync"][0]
        self.assertEqual(set(hesap["clientRoles"]["realm-management"]), beklenen)
        for yasak in ("manage-realm", "manage-clients", "realm-admin", "impersonation", "manage-identity-providers"):
            self.assertNotIn(yasak, eslemeler[0]["roles"])

    def test_yonetim_rolleri_yalniz_ayri_kapsamda(self):
        eslemeler = self.realm["clientScopeMappings"]["realm-management"]
        kapsamlar = {e["clientScope"] for e in eslemeler}
        self.assertEqual(kapsamlar, {"admin-api"})
        self.assertNotIn("admin-api", self.istemciler["identity-sync"]["defaultClientScopes"])
        self.assertIn("admin-api", self.istemciler["identity-sync"]["optionalClientScopes"])
        self.assertIn("kc-admin-api", self.istemciler["identity-sync"]["optionalClientScopes"])
        for ad in ("press-service", "site-kiraci1", "press"):
            self.assertNotIn("admin-api", self.istemciler[ad].get("optionalClientScopes", []), ad)
            self.assertNotIn("kc-admin-api", self.istemciler[ad].get("optionalClientScopes", []), ad)
            self.assertNotIn("kc-admin-api", self.istemciler[ad].get("defaultClientScopes", []), ad)

    def test_parola_listesi_var_ve_unix_satir_sonu(self):
        veri = PAROLA_LISTESI.read_bytes()
        self.assertNotIn(b"\r", veri)
        self.assertTrue(veri.endswith(b"\n"))
        self.assertGreater(veri.count(b"\n"), 100)


class ComposeFileTest(unittest.TestCase):
    def test_image_tag_is_unique_per_pane(self):
        # Parallel Panes build the same image. The tag must include the Pane port (KC_PORT = PANE_PORT).
        compose = (KLASOR.parents[1] / "dev" / "compose.keycloak.yaml").read_text(encoding="utf-8")
        self.assertRegex(compose, r"image: fs-keycloak-atonota:dev-\$\{KC_PORT:\?\}")


class OrnekKullaniciTesti(unittest.TestCase):
    def test_ornek_kullanicilar_ayri_dosyada_ve_example_test(self):
        veri = kullanicilari_oku()
        self.assertEqual(veri["realm"], "platform")
        self.assertEqual(KULLANICI_DOSYASI.name, "platform-users-0.json")
        self.assertGreaterEqual(len(veri["users"]), 1)
        for kullanici in veri["users"]:
            self.assertTrue(kullanici["email"].endswith("@example.test"), kullanici["email"])
            self.assertTrue(kullanici["username"].endswith("@example.test"), kullanici["username"])


class OrnekEnvTesti(unittest.TestCase):
    def test_realm_yer_tutuculari_ornek_env_dosyasinda(self):
        metin = REALM_DOSYASI.read_text(encoding="utf-8")
        anahtarlar = set(re.findall(r"\$\{([A-Z0-9_]+)\}", metin))
        self.assertTrue(anahtarlar)
        ornek = ORNEK_ENV.read_text(encoding="utf-8")
        env_anahtarlari = set(re.findall(r"^([A-Z0-9_]+)=", ornek, re.M))
        # Betiğin PANE_PORT'tan türettiği anahtarlar örnek dosyada "# Türetilen:" satırında yazılıdır.
        for satir in ornek.splitlines():
            if satir.startswith("# Türetilen:"):
                env_anahtarlari |= set(satir.split(":", 1)[1].split())
        self.assertTrue(anahtarlar <= env_anahtarlari, anahtarlar - env_anahtarlari)


if __name__ == "__main__":
    unittest.main()
