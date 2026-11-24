"""Realm dosyalarının depo kurallarını sınar. Keycloak gerekmez.

Beklenen değerler docs/sozlesmeler.md 2. bölümünden ve görev belgesinden alındı.
"""

import hashlib
import re
import unittest

from helpers import DIRECTORY, USER_FILE, EXAMPLE_ENV, PASSWORD_LIST, REALM_FILE, read_users, read_realm

PLACEHOLDER = re.compile(r"^\$\{[A-Z0-9_]+\}$")
CLIENTS = {"site-tenant1", "press", "identity-sync", "press-service"}
AUDIENCE_SCOPES = {"aud-site-tenant1": "site-tenant1", "aud-press": "press"}


class RealmFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = read_realm()
        cls.clients = {i["clientId"]: i for i in cls.realm.get("clients", [])}
        cls.scopes = {k["name"]: k for k in cls.realm.get("clientScopes", [])}

    def test_filename_matches_realm_name(self):
        # Keycloak dizin içe alımı <realm>-realm.json adını ister (DirImportProvider.java:138).
        self.assertEqual(self.realm["realm"], "platform")
        self.assertEqual(REALM_FILE.name, "platform-realm.json")

    def test_display_name_and_languages(self):
        # D-4, O-51: the brand name comes from a variable. The value is "AtonotA Login" (test_realm_backlog).
        self.assertEqual(self.realm["displayName"], "${IDENTITY_BRAND_NAME}")
        self.assertTrue(self.realm["internationalizationEnabled"])
        self.assertEqual(self.realm["defaultLocale"], "tr")
        self.assertEqual(set(self.realm["supportedLocales"]), {"tr", "en"})

    def test_login_and_email_use_project_theme(self):
        # Sözleşme 2. bölüm: giriş ve e-posta teması atonota adını taşır. Tema kimlik-tema işinden gelir.
        self.assertEqual(self.realm["loginTheme"], "atonota")
        self.assertEqual(self.realm["emailTheme"], "atonota")

    def test_clients_exist(self):
        self.assertTrue(CLIENTS <= set(self.clients), set(self.clients))

    def test_mobile_app_can_request_tenant_audience_and_mobile_scope(self):
        mobile = self.clients["mobile-app"]
        self.assertEqual(set(mobile["optionalClientScopes"]), {"aud-site-tenant1", "mobile"})
        self.assertNotIn("aud-site-tenant1", mobile["defaultClientScopes"])
        scope = self.scopes["mobile"]
        self.assertEqual(scope["protocol"], "openid-connect")
        self.assertEqual(scope["attributes"]["include.in.token.scope"], "true")
        self.assertFalse(scope.get("protocolMappers"))
        for name, client in self.clients.items():
            if name != "mobile-app":
                self.assertNotIn("mobile", client.get("defaultClientScopes", []))
                self.assertNotIn("mobile", client.get("optionalClientScopes", []))

    def test_browser_headers_deny_framing_and_restrict_document_actions(self):
        headers = self.realm["browserSecurityHeaders"]
        self.assertEqual(headers["xFrameOptions"], "DENY")
        directives = {part.strip() for part in headers["contentSecurityPolicy"].split(";")}
        self.assertTrue({
            "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'",
        } <= directives)

    def test_audience_scopes_add_one_audience(self):
        for name, audience in AUDIENCE_SCOPES.items():
            scope = self.scopes[name]
            mappers = [m for m in scope["protocolMappers"] if m["protocolMapper"] == "oidc-audience-mapper"]
            self.assertEqual(len(mappers), 1, name)
            self.assertEqual(mappers[0]["config"]["included.client.audience"], audience)
            self.assertEqual(mappers[0]["config"]["access.token.claim"], "true")

    def test_audience_scopes_are_optional(self):
        for client in self.clients.values():
            for name in AUDIENCE_SCOPES:
                self.assertNotIn(name, client.get("defaultClientScopes", []), client["clientId"])

    def test_service_client_scopes_match_contract(self):
        self.assertIn("aud-site-tenant1", self.clients["identity-sync"]["optionalClientScopes"])
        self.assertIn("aud-press", self.clients["identity-sync"]["optionalClientScopes"])
        self.assertIn("aud-site-tenant1", self.clients["press-service"]["optionalClientScopes"])
        self.assertNotIn("aud-press", self.clients["press-service"]["optionalClientScopes"])

    def test_service_clients_do_not_use_full_scope(self):
        # Tam kapsam açık olsaydı hesap rolleri belirtece girer ve aud ikinci değer alırdı.
        for name in ("identity-sync", "press-service"):
            self.assertTrue(self.clients[name]["serviceAccountsEnabled"], name)
            self.assertFalse(self.clients[name]["standardFlowEnabled"], name)
            self.assertFalse(self.clients[name]["fullScopeAllowed"], name)

    def test_browser_clients_use_code_flow_and_exact_redirect(self):
        for name in ("site-tenant1", "press"):
            client = self.clients[name]
            self.assertTrue(client["standardFlowEnabled"], name)
            self.assertFalse(client["implicitFlowEnabled"], name)
            self.assertFalse(client["directAccessGrantsEnabled"], name)
            self.assertFalse(client["publicClient"], name)
            for address in client["redirectUris"]:
                self.assertNotIn("*", address, name)
            self.assertEqual(client["attributes"]["backchannel.logout.session.required"], "true", name)
            self.assertIn("backchannel.logout.url", client["attributes"], name)

    def test_tenant_client_callback_and_pkce(self):
        # Contract section 2 (66d9ad8): the tenant client returns to platform_core.api.auth.keycloak_callback
        # and requires PKCE with S256.
        client = self.clients["site-tenant1"]
        self.assertEqual(client["redirectUris"], ["${ATONOTA_SITE_TENANT1_URL}/api/method/platform_core.api.auth.keycloak_callback"])
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")

    def test_client_secrets_are_placeholders(self):
        for client in self.clients.values():
            if client["publicClient"]:
                continue
            self.assertRegex(client["secret"], PLACEHOLDER, client["clientId"])

    def test_google_provider_is_disabled_and_uses_placeholders(self):
        google = [s for s in self.realm["identityProviders"] if s["alias"] == "google"]
        self.assertEqual(len(google), 1)
        self.assertFalse(google[0]["enabled"])
        self.assertRegex(google[0]["config"]["clientId"], PLACEHOLDER)
        self.assertRegex(google[0]["config"]["clientSecret"], PLACEHOLDER)

    def test_g78_policies(self):
        r = self.realm
        self.assertTrue(r["loginWithEmailAllowed"])
        self.assertTrue(r["verifyEmail"])
        self.assertTrue(r["bruteForceProtected"])
        self.assertEqual(r["failureFactor"], 5)
        self.assertEqual(r["maxDeltaTimeSeconds"], 300)
        self.assertIn("length(12)", r["passwordPolicy"])
        self.assertIn("passwordHistory(", r["passwordPolicy"])
        self.assertIn("passwordBlacklist(common-passwords.txt)", r["passwordPolicy"])
        # O-25 replaced the G-78 web lifetimes: the realm carries the customer values (7 days, 30 days).
        # Employee clients have 1 hour and 24 hours (test_session_lifetimes).
        self.assertEqual(r["ssoSessionIdleTimeout"], 7 * 24 * 60 * 60)
        self.assertEqual(r["ssoSessionMaxLifespan"], 30 * 24 * 60 * 60)
        self.assertEqual(r["accessTokenLifespan"], 5 * 60)
        self.assertTrue(r["revokeRefreshToken"])
        self.assertEqual(r["refreshTokenMaxReuse"], 0)
        self.assertFalse(r["rememberMe"])

    def test_signature_algorithm_is_rs256(self):
        # Sözleşme 3. bölüm: kitaplık yalnız RS256 kabul eder. Realm de RS256 ile imzalar.
        self.assertEqual(self.realm["defaultSignatureAlgorithm"], "RS256")

    def test_totp_and_passkey(self):
        self.assertEqual(self.realm["otpPolicyType"], "totp")
        self.assertTrue(self.realm["webAuthnPolicyPasswordlessPasskeysEnabled"])
        # The passkey dialog shows the same product name as the login page (O-51).
        self.assertEqual(self.realm["webAuthnPolicyPasswordlessRpEntityName"], "${IDENTITY_BRAND_NAME}")

    def test_realm_file_has_no_users(self):
        for user in self.realm.get("users", []):
            self.assertIn("serviceAccountClientId", user, user.get("username"))
            self.assertNotIn("email", user)
            self.assertNotIn("credentials", user)

    def test_identity_sync_has_least_privilege(self):
        # Contract 26a274c: identity-sync writes users (invites) and organizations (membership).
        # Minimum set verified in Keycloak 26.8.2 (docs/kararlar/0003-keycloak-eklentileri.md).
        beklenen = {"view-users", "query-users", "manage-users", "view-organizations", "manage-organizations", "view-identity-providers"}
        mappers = self.realm["clientScopeMappings"]["realm-management"]
        self.assertEqual(set(mappers[0]["roles"]), beklenen)
        account = [u for u in self.realm["users"] if u.get("serviceAccountClientId") == "identity-sync"][0]
        self.assertEqual(set(account["clientRoles"]["realm-management"]), beklenen)
        for yasak in ("manage-realm", "manage-clients", "realm-admin", "impersonation", "manage-identity-providers"):
            self.assertNotIn(yasak, mappers[0]["roles"])

    def test_admin_roles_require_separate_scope(self):
        mappers = self.realm["clientScopeMappings"]["realm-management"]
        scopes = {e["clientScope"] for e in mappers}
        self.assertEqual(scopes, {"admin-api"})
        self.assertNotIn("admin-api", self.clients["identity-sync"]["defaultClientScopes"])
        self.assertIn("admin-api", self.clients["identity-sync"]["optionalClientScopes"])
        self.assertIn("kc-admin-api", self.clients["identity-sync"]["optionalClientScopes"])
        for name in ("press-service", "site-tenant1", "press"):
            self.assertNotIn("admin-api", self.clients[name].get("optionalClientScopes", []), name)
            self.assertNotIn("kc-admin-api", self.clients[name].get("optionalClientScopes", []), name)
            self.assertNotIn("kc-admin-api", self.clients[name].get("defaultClientScopes", []), name)

    def test_password_list_exists_with_unix_line_endings(self):
        request_body = PASSWORD_LIST.read_bytes()
        self.assertNotIn(b"\r", request_body)
        self.assertTrue(request_body.endswith(b"\n"))
        self.assertGreater(request_body.count(b"\n"), 100)

    def test_password_list_has_no_email_shaped_entries(self):
        # The repository is public. An "@" followed by a domain may be a real address.
        email_shaped = re.compile(r"@[^@\s]+\.[A-Za-z]{2,}")
        lines = PASSWORD_LIST.read_text(encoding="utf-8").splitlines()
        found = [number for number, line in enumerate(lines, 1) if email_shaped.search(line)]
        self.assertEqual(found, [], "email-shaped entries at these line numbers")

    def test_password_list_matches_digest_in_source_note(self):
        # SOURCE.md pins the reviewed list. Any edit to the list must update the note.
        note = (PASSWORD_LIST.parent / "SOURCE.md").read_text(encoding="utf-8")
        pinned = re.search(r"SHA-256 özeti `([0-9a-f]{64})`", note)
        self.assertIsNotNone(pinned, "SOURCE.md must pin the list digest")
        self.assertEqual(hashlib.sha256(PASSWORD_LIST.read_bytes()).hexdigest(), pinned.group(1))


class ComposeFileTest(unittest.TestCase):
    def test_image_tag_is_unique_per_pane(self):
        # Shared stacks use the worktree namespace. Standalone runs use the Pane port.
        compose = (DIRECTORY.parents[1] / "dev" / "compose.keycloak.yaml").read_text(encoding="utf-8")
        self.assertIn("    image: fs-keycloak-atonota:dev-${FS_STACK_IMAGE_TAG:-${KC_PORT:?}}", compose.splitlines())
        self.assertIn("    image: fs-kimlik-realm-event-sink:${FS_STACK_IMAGE_TAG:-dev}", compose.splitlines())


class ExampleUserTest(unittest.TestCase):
    def test_imported_users_receive_the_same_default_role_as_new_users(self):
        default_role = read_realm()["defaultRole"]["name"]
        for user in read_users()["users"]:
            with self.subTest(username=user["username"]):
                self.assertEqual(user.get("realmRoles"), [default_role])

    def test_example_users_are_in_separate_file_with_example_test_domain(self):
        request_body = read_users()
        self.assertEqual(request_body["realm"], "platform")
        self.assertEqual(USER_FILE.name, "platform-users-0.json")
        self.assertGreaterEqual(len(request_body["users"]), 1)
        for user in request_body["users"]:
            self.assertTrue(user["email"].endswith("@example.test"), user["email"])
            self.assertTrue(user["username"].endswith("@example.test"), user["username"])


class ExampleEnvTest(unittest.TestCase):
    def test_example_env_lists_realm_placeholders(self):
        metin = REALM_FILE.read_text(encoding="utf-8")
        keys = set(re.findall(r"\$\{([A-Z0-9_]+)\}", metin))
        self.assertTrue(keys)
        example = EXAMPLE_ENV.read_text(encoding="utf-8")
        env_anahtarlari = set(re.findall(r"^([A-Z0-9_]+)=", example, re.M))
        # Betiğin PANE_PORT'tan türettiği anahtarlar örnek dosyada "# Türetilen:" satırında yazılıdır.
        for line in example.splitlines():
            if line.startswith("# Türetilen:"):
                env_anahtarlari |= set(line.split(":", 1)[1].split())
        self.assertTrue(keys <= env_anahtarlari, keys - env_anahtarlari)


if __name__ == "__main__":
    unittest.main()
