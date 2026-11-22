"""Çalışan Keycloak ile belirteç ve realm testleri.

Beklenen değerler docs/sozlesmeler.md 2. bölümünden alındı. Testler bin/kc-dev.sh test ile çalışır.
Keycloak yoksa testler atlanır ve not_run sayılır.
"""

import unittest

from yardimci import admin, canli_var_mi, istek, istemci_belirteci, jwt_govdesi, ortam, yonetici_belirteci

LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


def aud_listesi(govde: dict) -> list:
    aud = govde.get("aud")
    if aud is None:
        return []
    return aud if isinstance(aud, list) else [aud]


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class ServisBelirteciTesti(unittest.TestCase):
    def belirtec(self, istemci: str, sir_adi: str, kapsam=None) -> dict:
        yanit = istemci_belirteci(istemci, ortam(sir_adi), kapsam)
        self.assertEqual(yanit.durum, 200, yanit.govde[:300])
        return yanit.json()

    def test_identity_sync_kiraci_kapsamiyla_tek_aud_alir(self):
        veri = self.belirtec("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-site-kiraci1")
        govde = jwt_govdesi(veri["access_token"])
        self.assertEqual(govde["aud"], "site-kiraci1")
        self.assertEqual(govde["azp"], "identity-sync")
        self.assertEqual(govde["iss"], f"{ortam('KC_PUBLIC_URL')}/realms/platform")
        self.assertLessEqual(govde["exp"] - govde["iat"], 300)

    def test_kapsam_istenmezse_kiraci_aud_yok(self):
        veri = self.belirtec("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET")
        self.assertNotIn("site-kiraci1", aud_listesi(jwt_govdesi(veri["access_token"])))

    def test_identity_sync_press_kapsamiyla_tek_aud_alir(self):
        veri = self.belirtec("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-press")
        self.assertEqual(jwt_govdesi(veri["access_token"])["aud"], "press")

    def test_kiraci_belirtecinde_yonetim_yetkisi_yok(self):
        veri = self.belirtec("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-site-kiraci1")
        govde = jwt_govdesi(veri["access_token"])
        self.assertNotIn("realm-management", govde.get("resource_access", {}))
        self.assertNotIn("account", govde.get("resource_access", {}))
        self.assertEqual(aud_listesi(govde), ["site-kiraci1"])
        # Gerçek giriş yolu: Admin API bu belirteci reddetmeli (D-6).
        yanit = admin("/users?max=1", veri["access_token"])
        self.assertIn(yanit.durum, (401, 403), yanit.govde[:200])

    def test_yonetim_yetkisi_yalniz_ayri_kapsamda(self):
        # Keycloak 26.8 Admin API'si belirteçte kc-admin-api kapsamını ve Admin API hedefini ister
        # (Upgrading Guide, "Admin REST API audience"). Roller admin-api kapsamından gelir.
        veri = self.belirtec("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "admin-api kc-admin-api")
        govde = jwt_govdesi(veri["access_token"])
        roller = set(govde["resource_access"]["realm-management"]["roles"])
        # view-organizations bileşik roldür. Keycloak alt rolü (query-organizations) de açar.
        self.assertTrue({"manage-users", "manage-clients", "view-organizations"} <= roller, roller)
        self.assertIn("realm-management", aud_listesi(govde))
        self.assertIn(f"{ortam('KC_PUBLIC_URL')}/admin/realms/platform", aud_listesi(govde))
        self.assertNotIn("site-kiraci1", aud_listesi(govde))
        self.assertEqual(admin("/users?max=1", veri["access_token"]).durum, 200)

    def test_yonetim_rolleri_kc_admin_api_olmadan_admin_api_acmaz(self):
        veri = self.belirtec("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "admin-api")
        self.assertIn(admin("/users?max=1", veri["access_token"]).durum, (401, 403))

    def test_press_service_kiraci_kapsami_alir_press_kapsami_alamaz(self):
        veri = self.belirtec("press-service", "ATONOTA_PRESS_SERVICE_SECRET", "aud-site-kiraci1")
        self.assertEqual(jwt_govdesi(veri["access_token"])["aud"], "site-kiraci1")
        # Sözleşme: aud-press kapsamını yalnız identity-sync kullanır. press-service hiçbir yolla
        # press hedefli belirteç alamaz. Keycloak 26.8.2 isteği invalid_scope ile reddeder.
        yanit = istemci_belirteci("press-service", ortam("ATONOTA_PRESS_SERVICE_SECRET"), "aud-press")
        if yanit.durum == 200:
            self.assertNotIn("press", aud_listesi(jwt_govdesi(yanit.json()["access_token"])))
        else:
            self.assertEqual(yanit.durum, 400, yanit.govde[:200])
            self.assertEqual(yanit.json()["error"], "invalid_scope")

    def test_yanlis_sir_reddedilir(self):
        yanit = istemci_belirteci("identity-sync", "yanlis-sir", "aud-site-kiraci1")
        self.assertEqual(yanit.durum, 401)

    def test_iss_well_known_ile_ayni(self):
        yanit = istek("GET", f"{ortam('KC_PUBLIC_URL')}/realms/platform/.well-known/openid-configuration")
        self.assertEqual(yanit.durum, 200)
        self.assertEqual(yanit.json()["issuer"], f"{ortam('KC_PUBLIC_URL')}/realms/platform")


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class RealmAyarlariTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yonetici = yonetici_belirteci()
        yanit = admin("", cls.yonetici)
        assert yanit.durum == 200, yanit.govde[:200]
        cls.realm = yanit.json()

    def test_marka_dil_tema(self):
        r = self.realm
        self.assertEqual(r["displayName"], "Atonota")
        self.assertEqual(r["defaultLocale"], "tr")
        self.assertEqual(set(r["supportedLocales"]), {"tr", "en"})
        self.assertEqual(r["loginTheme"], "atonota")
        self.assertEqual(r["emailTheme"], "atonota")

    def test_g78_politikalari_yuklendi(self):
        r = self.realm
        self.assertTrue(r["loginWithEmailAllowed"])
        self.assertTrue(r["verifyEmail"])
        self.assertTrue(r["bruteForceProtected"])
        self.assertEqual(r["failureFactor"], 5)
        self.assertEqual(r["maxDeltaTimeSeconds"], 300)
        self.assertIn("length(12)", r["passwordPolicy"])
        self.assertIn("passwordBlacklist(yaygin-parolalar.txt)", r["passwordPolicy"])
        self.assertEqual(r["ssoSessionIdleTimeout"], 1800)
        self.assertEqual(r["ssoSessionMaxLifespan"], 43200)
        self.assertEqual(r["accessTokenLifespan"], 300)
        self.assertTrue(r["revokeRefreshToken"])
        self.assertEqual(r["refreshTokenMaxReuse"], 0)
        self.assertFalse(r["rememberMe"])

    def test_totp_ve_passkey_acik(self):
        self.assertEqual(self.realm["otpPolicyType"], "totp")
        self.assertTrue(self.realm["webAuthnPolicyPasswordlessPasskeysEnabled"])
        eylemler = {e["alias"]: e for e in admin("/authentication/required-actions", self.yonetici).json()}
        self.assertTrue(eylemler["CONFIGURE_TOTP"]["enabled"])
        self.assertTrue(eylemler["webauthn-register-passwordless"]["enabled"])
        yurutmeler = admin("/authentication/flows/browser/executions", self.yonetici).json()
        otp = [y for y in yurutmeler if y.get("providerId") == "auth-otp-form"]
        self.assertEqual(len(otp), 1)
        self.assertEqual(otp[0]["requirement"], "ALTERNATIVE")

    def test_sirlar_ortamdan_geldi(self):
        yanit = admin("/clients?clientId=identity-sync", self.yonetici)
        kimlik = yanit.json()[0]["id"]
        sir = admin(f"/clients/{kimlik}/client-secret", self.yonetici).json()["value"]
        self.assertEqual(sir, ortam("ATONOTA_IDENTITY_SYNC_SECRET"))
        self.assertFalse(sir.startswith("${"))

    def test_donus_adresleri_ortamdan_geldi(self):
        kiraci = admin("/clients?clientId=site-kiraci1", self.yonetici).json()[0]
        self.assertEqual(
            kiraci["redirectUris"],
            [f"{ortam('ATONOTA_SITE_KIRACI1_URL')}/api/method/frappe.integrations.oauth2_logins.login_via_keycloak"],
        )
        self.assertEqual(
            kiraci["attributes"]["backchannel.logout.url"],
            f"{ortam('ATONOTA_SITE_KIRACI1_URL')}/api/method/platform_core.api.keycloak_backchannel_logout",
        )
        press = admin("/clients?clientId=press", self.yonetici).json()[0]
        self.assertEqual(press["redirectUris"], [f"{ortam('ATONOTA_PRESS_URL')}/api/method/press_tr.api.auth.keycloak_callback"])

    def test_google_kapali(self):
        google = admin("/identity-provider/instances/google", self.yonetici).json()
        self.assertFalse(google["enabled"])

    def test_ornek_kullanicilar_yuklendi(self):
        kullanicilar = admin("/users?email=example.test&max=50", self.yonetici).json()
        self.assertGreaterEqual(len(kullanicilar), 1)
        for k in kullanicilar:
            self.assertTrue(k["email"].endswith("@example.test"))

    def test_imza_algoritmasi_rs256(self):
        self.assertEqual(self.realm["defaultSignatureAlgorithm"], "RS256")

    def test_anonim_istemci_kaydi_kapali(self):
        # G-144: anonim dinamik istemci kaydı kapalı kalır. Gerçek uçla denenir (D-6).
        yanit = istek(
            "POST",
            f"{ortam('KC_PUBLIC_URL')}/realms/platform/clients-registrations/default",
            govde={"clientId": "saldirgan-istemci", "redirectUris": ["https://kotu.example/*"]},
        )
        self.assertIn(yanit.durum, (401, 403), yanit.govde[:200])
        self.assertEqual(admin("/clients?clientId=saldirgan-istemci", self.yonetici).json(), [])

    def test_eposta_mailpit_uzerinden(self):
        self.assertEqual(self.realm["smtpServer"]["host"], ortam("ATONOTA_SMTP_HOST"))


if __name__ == "__main__":
    unittest.main()
