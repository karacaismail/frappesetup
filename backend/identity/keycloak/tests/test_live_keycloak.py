"""Çalışan Keycloak ile belirteç ve realm testleri.

Beklenen değerler docs/sozlesmeler.md 2. bölümünden alındı. Testler bin/kc-dev.sh test ile çalışır.
Keycloak yoksa testler atlanır ve not_run sayılır.
"""

import hmac
import unittest
import urllib.parse

from helpers import admin, assert_refused_without_pkce, live_available, get_without_redirect, request, client_token, jwt_payload, get_environment_value, admin_token, safe_detail

LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


def audiences(body: dict) -> list:
    aud = body.get("aud")
    if aud is None:
        return []
    return aud if isinstance(aud, list) else [aud]


@unittest.skipUnless(live_available(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class ServiceTokenTest(unittest.TestCase):
    @classmethod
    def administrator_token(cls) -> str:
        return admin_token()

    def token(self, client: str, secret_name: str, scope=None) -> dict:
        response = client_token(client, get_environment_value(secret_name), scope)
        self.assertEqual(response.status, 200, safe_detail(response))
        return response.json()

    def test_identity_sync_gets_only_tenant_audience_with_tenant_scope(self):
        request_body = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-site-tenant1")
        body = jwt_payload(request_body["access_token"])
        self.assertEqual(body["aud"], "site-tenant1")
        self.assertEqual(body["azp"], "identity-sync")
        self.assertEqual(body["iss"], f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform")
        self.assertLessEqual(body["exp"] - body["iat"], 300)

    def test_missing_scope_excludes_tenant_audience(self):
        request_body = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET")
        self.assertNotIn("site-tenant1", audiences(jwt_payload(request_body["access_token"])))

    def test_identity_sync_gets_only_press_audience_with_press_scope(self):
        request_body = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-press")
        self.assertEqual(jwt_payload(request_body["access_token"])["aud"], "press")

    def test_tenant_token_has_no_admin_permission(self):
        request_body = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-site-tenant1")
        body = jwt_payload(request_body["access_token"])
        self.assertNotIn("realm-management", body.get("resource_access", {}))
        self.assertNotIn("account", body.get("resource_access", {}))
        self.assertEqual(audiences(body), ["site-tenant1"])
        # Gerçek giriş yolu: Admin API bu belirteci reddetmeli (D-6).
        response = admin("/users?max=1", request_body["access_token"])
        # Contract section 2 accepts either authorization rejection.
        self.assertIn(response.status, (401, 403), safe_detail(response))

    def test_admin_permission_requires_separate_scope(self):
        # Keycloak 26.8 Admin API'si belirteçte kc-admin-api kapsamını ve Admin API hedefini ister
        # (Upgrading Guide, "Admin REST API audience"). Roller admin-api kapsamından gelir.
        request_body = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "admin-api kc-admin-api")
        body = jwt_payload(request_body["access_token"])
        roles = set(body["resource_access"]["realm-management"]["roles"])
        # Contract 26a274c: user and organization write roles, nothing realm-wide.
        self.assertTrue({"view-users", "query-users", "manage-users", "view-organizations", "manage-organizations"} <= roles, roles)
        self.assertFalse({"manage-realm", "manage-clients", "realm-admin", "impersonation"} & roles, roles)
        self.assertIn("realm-management", audiences(body))
        self.assertIn(f"{get_environment_value('KC_PUBLIC_URL')}/admin/realms/platform", audiences(body))
        self.assertNotIn("site-tenant1", audiences(body))
        self.assertEqual(admin("/users?max=1", request_body["access_token"]).status, 200)

    def test_identity_sync_admin_scope_can_create_user_and_organization(self):
        # D-6 on the real Admin API: the admin-api token creates a user and an organization; the
        # A tenant-scoped token of the same account cannot open the Admin API.
        token = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "admin-api kc-admin-api")["access_token"]
        admin_token = self.__class__.administrator_token()
        user = "davet-denemesi@example.test"
        for u in admin(f"/users?username={user}&exact=true", admin_token).json():
            admin(f"/users/{u['id']}", admin_token, method="DELETE")
        created = admin("/users", token, method="POST", body={"username": user, "email": user, "enabled": True})
        self.assertEqual(created.status, 201, safe_detail(created))
        kuruluslar = admin("/organizations?search=deneme-kurulus&exact=true", admin_token).json()
        for k in kuruluslar:
            admin(f"/organizations/{k['id']}", admin_token, method="DELETE")
        kurulus = admin("/organizations", token, method="POST",
                        body={"name": "deneme-kurulus", "alias": "deneme-kurulus", "domains": [{"name": "deneme-kurulus.example.test"}]})
        self.assertEqual(kurulus.status, 201, safe_detail(kurulus))
        # Realm-wide writes stay forbidden for this account.
        self.assertEqual(admin("/clients", token, method="POST", body={"clientId": "yetki-denemesi"}).status, 403)
        # Cleanup with the master admin.
        for u in admin(f"/users?username={user}&exact=true", admin_token).json():
            admin(f"/users/{u['id']}", admin_token, method="DELETE")
        for k in admin("/organizations?search=deneme-kurulus&exact=true", admin_token).json():
            admin(f"/organizations/{k['id']}", admin_token, method="DELETE")

    def test_admin_roles_require_keycloak_admin_api_scope(self):
        request_body = self.token("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "admin-api")
        response = admin("/users?max=1", request_body["access_token"])
        # Without kc-admin-api, the Admin API audience check rejects the token.
        self.assertEqual(response.status, 401, safe_detail(response))

    def test_press_service_accepts_only_tenant_scope(self):
        request_body = self.token("press-service", "ATONOTA_PRESS_SERVICE_SECRET", "aud-site-tenant1")
        self.assertEqual(jwt_payload(request_body["access_token"])["aud"], "site-tenant1")
        # Sözleşme: aud-press kapsamını yalnız identity-sync kullanır. press-service hiçbir yolla
        # press hedefli belirteç alamaz. Keycloak 26.8.2 isteği invalid_scope ile reddeder.
        response = client_token("press-service", get_environment_value("ATONOTA_PRESS_SERVICE_SECRET"), "aud-press")
        self.assertEqual(safe_detail(response), "HTTP 400 invalid_scope")

    def test_wrong_secret_is_rejected(self):
        response = client_token("identity-sync", "yanlis-sir", "aud-site-tenant1")
        self.assertEqual(response.status, 401)

    def test_iss_matches_well_known(self):
        response = request("GET", f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform/.well-known/openid-configuration")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["issuer"], f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform")


@unittest.skipUnless(live_available(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class RealmSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_token = admin_token()
        response = admin("", cls.admin_token)
        assert response.status == 200, safe_detail(response)
        cls.realm = response.json()

    def test_marka_dil_tema(self):
        r = self.realm
        self.assertEqual(r["displayName"], "Atonota")
        self.assertEqual(r["defaultLocale"], "tr")
        self.assertEqual(set(r["supportedLocales"]), {"tr", "en"})
        self.assertEqual(r["loginTheme"], "atonota")
        self.assertEqual(r["emailTheme"], "atonota")

    def test_g78_policies_are_loaded(self):
        r = self.realm
        self.assertTrue(r["loginWithEmailAllowed"])
        self.assertTrue(r["verifyEmail"])
        self.assertTrue(r["bruteForceProtected"])
        self.assertEqual(r["failureFactor"], 5)
        self.assertEqual(r["maxDeltaTimeSeconds"], 300)
        self.assertIn("length(12)", r["passwordPolicy"])
        self.assertIn("passwordBlacklist(common-passwords.txt)", r["passwordPolicy"])
        # O-25: customer lifetimes on the realm; employee clients carry 1 hour and 24 hours.
        self.assertEqual(r["ssoSessionIdleTimeout"], 7 * 24 * 3600)
        self.assertEqual(r["ssoSessionMaxLifespan"], 30 * 24 * 3600)
        self.assertEqual(r["accessTokenLifespan"], 300)
        self.assertTrue(r["revokeRefreshToken"])
        self.assertEqual(r["refreshTokenMaxReuse"], 0)
        self.assertFalse(r["rememberMe"])

    def test_totp_and_passkey_enabled(self):
        self.assertEqual(self.realm["otpPolicyType"], "totp")
        self.assertTrue(self.realm["webAuthnPolicyPasswordlessPasskeysEnabled"])
        eylemler = {e["alias"]: e for e in admin("/authentication/required-actions", self.admin_token).json()}
        self.assertTrue(eylemler["CONFIGURE_TOTP"]["enabled"])
        self.assertTrue(eylemler["webauthn-register-passwordless"]["enabled"])
        yurutmeler = admin("/authentication/flows/browser/executions", self.admin_token).json()
        otp = [y for y in yurutmeler if y.get("providerId") == "auth-otp-form"]
        self.assertEqual(len(otp), 1)
        self.assertEqual(otp[0]["requirement"], "ALTERNATIVE")

    def test_secrets_come_from_environment(self):
        response = admin("/clients?clientId=identity-sync", self.admin_token)
        identity = response.json()[0]["id"]
        secret = admin(f"/clients/{identity}/client-secret", self.admin_token).json()["value"]
        # Compare without printing either value on failure; the values are secrets.
        self.assertTrue(hmac.compare_digest(secret, get_environment_value("ATONOTA_IDENTITY_SYNC_SECRET")), "client secret differs from .env")
        self.assertFalse(secret.startswith("${"))

    def test_redirect_uris_come_from_environment(self):
        tenant = admin("/clients?clientId=site-tenant1", self.admin_token).json()[0]
        self.assertEqual(
            tenant["redirectUris"],
            [f"{get_environment_value('ATONOTA_SITE_TENANT1_URL')}/api/method/platform_core.api.auth.keycloak_callback"],
        )
        self.assertEqual(tenant["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertEqual(
            tenant["attributes"]["backchannel.logout.url"],
            f"{get_environment_value('ATONOTA_SITE_TENANT1_URL')}/api/method/platform_core.api.keycloak_backchannel_logout",
        )
        press = admin("/clients?clientId=press", self.admin_token).json()[0]
        self.assertEqual(press["redirectUris"], [f"{get_environment_value('ATONOTA_PRESS_URL')}/api/method/press_tr.api.auth.keycloak_callback"])

    def test_google_disabled(self):
        google = admin("/identity-provider/instances/google", self.admin_token).json()
        self.assertFalse(google["enabled"])

    def test_example_users_are_loaded(self):
        users = admin("/users?email=example.test&max=50", self.admin_token).json()
        self.assertGreaterEqual(len(users), 1)
        for k in users:
            self.assertTrue(k["email"].endswith("@example.test"))

    def test_signature_algorithm_is_rs256(self):
        self.assertEqual(self.realm["defaultSignatureAlgorithm"], "RS256")

    def test_anonymous_client_registration_is_disabled(self):
        # G-144: anonim dinamik istemci kaydı kapalı kalır. Gerçek uçla denenir (D-6).
        response = request(
            "POST",
            f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform/clients-registrations/default",
            body={"clientId": "saldirgan-istemci", "redirectUris": ["https://kotu.example/*"]},
        )
        self.assertIn(response.status, (401, 403), safe_detail(response))
        clients = admin("/clients?clientId=saldirgan-istemci", self.admin_token)
        self.assertTrue(clients.json() == [], safe_detail(clients))

    def test_tenant_authorize_without_pkce_is_refused(self):
        # D-6: the real authorize endpoint must refuse a tenant login request that carries no code_challenge.
        query = urllib.parse.urlencode({
            "client_id": "site-tenant1", "response_type": "code", "scope": "openid", "state": "s",
            "redirect_uri": f"{get_environment_value('ATONOTA_SITE_TENANT1_URL')}/api/method/platform_core.api.auth.keycloak_callback",
        })
        response = get_without_redirect(f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{query}")
        assert_refused_without_pkce(self, response)

    def test_email_goes_through_mailpit(self):
        self.assertEqual(self.realm["smtpServer"]["host"], get_environment_value("ATONOTA_SMTP_HOST"))


if __name__ == "__main__":
    unittest.main()
