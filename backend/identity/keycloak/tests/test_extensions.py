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

from helpers import DIRECTORY, EXAMPLE_ENV, admin, live_available, request, client_token, get_environment_value, read_realm, admin_token

DOCKERFILE = DIRECTORY / "Dockerfile"
PLACEHOLDER = re.compile(r"^\$\{[A-Z0-9_]+\}$")
MAGIC_LINK_AUTHENTICATOR = "skycloak-magic-link"
AKIS = "atonota-browser"
POST_BROKER = "atonota-post-broker"


class ExtensionFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = read_realm()
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    def test_eklenti_jarlari_sabit_surum_ve_ozetle_eklenir(self):
        # The sky-cloak extension is out (second review, E1 and E2). Apple jar and the cloudflight
        # magic link source archive are pinned by checksum; the Maven image is pinned by digest.
        self.assertNotIn("sky-cloak", self.dockerfile)
        self.assertIn("klausbetz/apple-identity-provider-keycloak/releases/download/1.17.0/", self.dockerfile)
        self.assertEqual(self.dockerfile.count("--checksum=sha256:"), 2)
        self.assertRegex(self.dockerfile, r"(?m)^ARG MAVEN_IMAGE=maven:[0-9.]+-eclipse-temurin-21@sha256:[0-9a-f]{64}$")
        self.assertIn("FROM ${MAVEN_IMAGE} AS magiclink-build", self.dockerfile)

    def test_browser_flow_has_no_magic_link(self):
        self.assertEqual(self.realm["browserFlow"], AKIS)
        yurutmeler = [y for a in self.realm["authenticationFlows"] for y in a["authenticationExecutions"]]
        self.assertEqual([y for y in yurutmeler if y.get("authenticator") == MAGIC_LINK_AUTHENTICATOR], [])
        password = [y for y in yurutmeler if y.get("authenticator") == "auth-username-password-form"]
        self.assertEqual(len(password), 1, "password path stays")
        otp = [y for y in yurutmeler if y.get("authenticator") == "auth-otp-form"]
        self.assertTrue(otp and all(o["requirement"] == "ALTERNATIVE" for o in otp))

    def test_social_providers_have_post_broker_second_factor(self):
        # O6: after a social login the second factor must be asked when the user has one.
        # O-51: the platform list is data. The rule covers every provider in the realm, not a fixed list.
        akislar = {a["alias"]: a for a in self.realm["authenticationFlows"]}
        self.assertTrue(self.realm["identityProviders"])
        for idp in self.realm["identityProviders"]:
            self.assertEqual(idp.get("postBrokerLoginFlowAlias"), POST_BROKER, idp["alias"])
        self.assertIn(POST_BROKER, akislar)
        alt = [y.get("flowAlias") for y in akislar[POST_BROKER]["authenticationExecutions"] if y.get("authenticatorFlow")]
        yurutmeler = [y for a in [akislar[POST_BROKER]] + [akislar[x] for x in alt] for y in a["authenticationExecutions"]]
        self.assertIn("conditional-user-configured", [y.get("authenticator") for y in yurutmeler])
        self.assertIn("auth-otp-form", [y.get("authenticator") for y in yurutmeler])

    def test_current_platforms_stay_in_the_realm(self):
        # Review 1, minor finding 4: the rule above covers every provider, so a deleted provider would
        # go unnoticed. Today's realm has these two. A new platform comes as data and is not listed here.
        aliases = {idp["alias"] for idp in self.realm["identityProviders"]}
        self.assertLessEqual({"google", "apple"}, aliases)

    def test_apple_provider_disabled_without_keys(self):
        apple = [s for s in self.realm["identityProviders"] if s["alias"] == "apple"]
        self.assertEqual(len(apple), 1)
        self.assertEqual(apple[0]["providerId"], "apple")
        self.assertFalse(apple[0]["enabled"])
        for anahtar in ("clientId", "clientSecret", "teamId", "keyId"):
            self.assertRegex(apple[0]["config"][anahtar], PLACEHOLDER, anahtar)
        env_anahtarlari = set(re.findall(r"^([A-Z0-9_]+)=", EXAMPLE_ENV.read_text(encoding="utf-8"), re.M))
        for anahtar in ("clientId", "clientSecret", "teamId", "keyId"):
            self.assertIn(apple[0]["config"][anahtar][2:-1], env_anahtarlari)


def _cookie_opener() -> urllib.request.OpenerDirector:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # yönlendirmeyi izleme, Location başlığını oku

    # Keycloak çerezleri Secure bayrağıyla verir. Tarayıcılar *.localhost adresini güvenli sayar ve
    # çerezi http üzerinden de gönderir. Python'un kavanozu aynı davranışı bu ayarla verir.
    kavanoz = CookieJar(DefaultCookiePolicy(secure_protocols=("https", "wss", "http")))
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(kavanoz), NoRedirect())


def _open(opener, address, request_body=None):
    """Yanıtı (durum, başlıklar, gövde) olarak döner. Yönlendirme izlenmez."""
    try:
        with opener.open(urllib.request.Request(address, data=request_body), timeout=30) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        with error:
            return error.code, dict(error.headers), error.read().decode("utf-8", "replace")


def _follow_keycloak_redirect(opener, address: str, kc: str):
    """Keycloak içindeki yönlendirmeleri izler. Keycloak dışına çıkan ilk adreste durur."""
    status, headers, body = _open(opener, address)
    for _ in range(5):
        location = headers.get("Location", "")
        if status not in (301, 302, 303) or not location.startswith(kc):
            break
        status, headers, body = _open(opener, location)
    return status, headers, body


def _form_action(html: str) -> str:
    eslesme = re.search(r'action="([^"]*login-actions/authenticate[^"]*)"', html)
    if not eslesme:
        raise AssertionError("giriş formu bulunamadı")
    return eslesme.group(1).replace("&amp;", "&")


@unittest.skipUnless(live_available(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class LiveExtensionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = get_environment_value("KC_PUBLIC_URL")
        cls.admin_token = admin_token()

    def test_extensions_loaded_on_server(self):
        bilgi = request("GET", f"{self.kc}/admin/serverinfo", token=self.admin_token).json()
        saglayicilar = bilgi["providers"]
        self.assertIn("apple", saglayicilar["social"]["providers"])
        # Passkey özelliği sunucuda açık olmalı. Yoksa realm'deki passkey ayarı etkisizdir.
        ozellikler = {o["name"]: o for o in bilgi.get("features", [])}
        self.assertIn("PASSKEYS", ozellikler, sorted(ozellikler))
        self.assertTrue(ozellikler["PASSKEYS"]["enabled"])

    def test_browser_flow_has_passkey_condition_and_otp(self):
        yurutmeler = admin(f"/authentication/flows/{AKIS}/executions", self.admin_token).json()
        saglayicilar = {y.get("providerId"): y for y in yurutmeler}
        self.assertEqual(saglayicilar["auth-otp-form"]["requirement"], "ALTERNATIVE")
        self.assertEqual(saglayicilar["conditional-credential"]["requirement"], "REQUIRED")
        self.assertEqual(saglayicilar["webauthn-authenticator"]["requirement"], "ALTERNATIVE")
        self.assertNotIn(MAGIC_LINK_AUTHENTICATOR, saglayicilar)
        self.assertEqual(saglayicilar["auth-username-password-form"]["requirement"], "REQUIRED")

    def test_browser_flow_bound_and_apple_disabled(self):
        realm = admin("", self.admin_token).json()
        self.assertEqual(realm["browserFlow"], AKIS)
        apple = admin("/identity-provider/instances/apple", self.admin_token).json()
        self.assertFalse(apple["enabled"])
        self.assertTrue(apple["hideOnLogin"])
        # O-56: development keeps the platform secrets empty, and a closed platform stores none.
        for key in ("clientId", "teamId", "keyId"):
            self.assertEqual(apple["config"].get(key, ""), "", key)

    def test_magic_link_endpoints_are_gone(self):
        # Acceptance for removing the extension: its realm resource no longer exists.
        saglik = request("GET", f"{self.kc}/realms/platform/skycloak-magic-link/health")
        self.assertEqual(saglik.status, 404)
        response = client_token("identity-sync", get_environment_value("ATONOTA_IDENTITY_SYNC_SECRET"), "admin-api kc-admin-api")
        self.assertEqual(response.status, 200)
        production = request(
            "POST",
            f"{self.kc}/realms/platform/skycloak-magic-link",
            body={"email": "ayse.ornek@example.test", "clientId": "site-tenant1", "redirectUri": "https://x.example", "send": False},
            token=response.json()["access_token"],
        )
        self.assertEqual(production.status, 404)
        bilgi = request("GET", f"{self.kc}/admin/serverinfo", token=self.admin_token).json()["providers"]
        self.assertNotIn(MAGIC_LINK_AUTHENTICATOR, bilgi["authenticator"]["providers"])

    def test_post_broker_flow_is_bound_to_social_providers(self):
        # O-51: every provider on the server, whatever the list holds.
        providers = admin("/identity-provider/instances", self.admin_token).json()
        self.assertTrue(providers)
        for idp in providers:
            self.assertEqual(idp.get("postBrokerLoginFlowAlias"), POST_BROKER, idp["alias"])
        yurutmeler = admin(f"/authentication/flows/{POST_BROKER}/executions", self.admin_token).json()
        saglayicilar = {y.get("providerId"): y for y in yurutmeler}
        self.assertIn("conditional-user-configured", saglayicilar)
        self.assertEqual(saglayicilar["auth-otp-form"]["requirement"], "ALTERNATIVE")


if __name__ == "__main__":
    unittest.main()
