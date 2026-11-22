"""Realm file rules from the gap backlog (backend/docs/gap-backlog.md, kimlik-realm items 2-12).

Expected values come from the backlog, the contract (docs/sozlesmeler.md section 2, d699082),
mobile.md GR-2 and GR-3, and project record O-25 and O-27. Keycloak is not needed.
"""

from __future__ import annotations

import re
import unittest
import urllib.parse

from yardimci import (KLASOR, ORNEK_ENV, admin, canli_var_mi, get_without_redirect, istemci_belirteci, istek,
                      jwt_govdesi, ortam, pkce_pair, realm_oku, yonetici_belirteci, safe_detail)

PLACEHOLDER = re.compile(r"^\$\{[A-Z0-9_]+\}$")
PRODUCTION_ENV = KLASOR / "production.env.example"
COMPOSE = KLASOR.parents[1] / "dev" / "compose.keycloak.yaml"
MOBILE_CLIENT = "mobile-app"
TENANT_SERVICE_CLIENTS = {"site-kiraci1"}
# Contract 42f8e32: press-service may also request aud-identity-sync.
IDENTITY_SYNC_AUDIENCE_CLIENTS = TENANT_SERVICE_CLIENTS | {"press-service"}


def _env_values(path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


class RealmBacklogFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.clients = {c["clientId"]: c for c in cls.realm["clients"]}
        cls.scopes = {s["name"]: s for s in cls.realm["clientScopes"]}
        cls.dev_env = _env_values(ORNEK_ENV)
        cls.prod_env = _env_values(PRODUCTION_ENV) if PRODUCTION_ENV.exists() else {}
        cls.compose = COMPOSE.read_text(encoding="utf-8")

    # Item 2: public mobile client, PKCE S256, no secret (mobile.md GR-2, GR-3).
    def test_mobile_client_is_public_with_pkce_and_no_secret(self):
        client = self.clients[MOBILE_CLIENT]
        self.assertTrue(client["publicClient"])
        self.assertNotIn("secret", client)
        self.assertTrue(client["standardFlowEnabled"])
        self.assertFalse(client["implicitFlowEnabled"])
        self.assertFalse(client["directAccessGrantsEnabled"])
        self.assertFalse(client["serviceAccountsEnabled"])
        self.assertFalse(client["fullScopeAllowed"])
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertEqual(client["attributes"].get("oauth2.device.authorization.grant.enabled"), "false")
        self.assertEqual(client["redirectUris"], ["${ATONOTA_MOBILE_REDIRECT_URI}"])
        self.assertTrue(self.dev_env["ATONOTA_MOBILE_REDIRECT_URI"].startswith("https://"))
        self.assertEqual(client["webOrigins"], [])

    # Item 3: the press client requires PKCE S256 too.
    def test_press_client_requires_pkce(self):
        self.assertEqual(self.clients["press"]["attributes"]["pkce.code.challenge.method"], "S256")

    # Item 4: every SMTP setting comes from the environment; production has TLS and authentication on.
    def test_smtp_settings_come_from_the_environment(self):
        smtp = self.realm["smtpServer"]
        for key in ("host", "port", "from", "auth", "ssl", "starttls", "user", "password"):
            self.assertRegex(smtp[key], PLACEHOLDER, key)
            name = smtp[key][2:-1]
            self.assertIn(name, self.dev_env, name)
            self.assertIn(f"{name}: ${{{name}:?}}", self.compose, name)

    def test_production_smtp_uses_tls_and_authentication(self):
        self.assertEqual(self.prod_env.get("ATONOTA_SMTP_AUTH"), "true")
        self.assertEqual(self.prod_env.get("ATONOTA_SMTP_STARTTLS"), "true")
        self.assertEqual(self.prod_env.get("ATONOTA_SMTP_SSL"), "false")  # STARTTLS on port 587
        self.assertEqual(self.prod_env.get("ATONOTA_SMTP_PORT"), "587")

    # Item 5: sslRequired is "all" in production, "external" in development.
    def test_ssl_required_comes_from_the_environment(self):
        self.assertEqual(self.realm["sslRequired"], "${ATONOTA_SSL_REQUIRED}")
        self.assertEqual(self.dev_env["ATONOTA_SSL_REQUIRED"], "external")
        self.assertEqual(self.prod_env.get("ATONOTA_SSL_REQUIRED"), "all")

    def test_production_example_covers_every_development_key(self):
        missing = set(self.dev_env) - set(self.prod_env)
        self.assertEqual(missing, set())

    # Item 10: the visible brand name comes from a variable (D-4).
    def test_brand_name_comes_from_a_variable(self):
        self.assertEqual(self.realm["displayName"], "${IDENTITY_BRAND_NAME}")
        self.assertEqual(self.realm["displayNameHtml"], "${IDENTITY_BRAND_NAME}")
        self.assertEqual(self.realm["smtpServer"]["fromDisplayName"], "${IDENTITY_BRAND_NAME}")
        self.assertEqual(self.dev_env["IDENTITY_BRAND_NAME"], "Atonota")
        # The account console theme reads the same variable from the Keycloak container (kimlik-tema request).
        self.assertIn("IDENTITY_BRAND_NAME: ${IDENTITY_BRAND_NAME:?}", self.compose)

    # kimlik-tema request 4: the account console uses the atonota theme; the image copies the whole theme.
    def test_account_theme_is_atonota_and_copied(self):
        self.assertEqual(self.realm["accountTheme"], "atonota")
        dockerfile = (KLASOR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY --chown=1000:0 themes/ /opt/keycloak/themes/", dockerfile)
        ignore = (KLASOR / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("!themes/**", ignore)
        self.assertFalse([line for line in ignore if "account" in line], ignore)

    # Item 12: aud-identity-sync adds only aud=identity-sync; only tenant service clients may ask for it.
    def test_identity_sync_audience_scope(self):
        scope = self.scopes["aud-identity-sync"]
        mappers = [m for m in scope["protocolMappers"] if m["protocolMapper"] == "oidc-audience-mapper"]
        self.assertEqual(len(mappers), 1)
        self.assertEqual(mappers[0]["config"]["included.client.audience"], "identity-sync")
        self.assertEqual(mappers[0]["config"]["access.token.claim"], "true")
        self.assertEqual(mappers[0]["config"]["id.token.claim"], "false")
        self.assertEqual(len(scope["protocolMappers"]), 1)

    def test_only_allowed_service_clients_may_request_identity_sync_audience(self):
        for client_id, client in self.clients.items():
            self.assertNotIn("aud-identity-sync", client.get("defaultClientScopes", []), client_id)
            optional = "aud-identity-sync" in client.get("optionalClientScopes", [])
            self.assertEqual(optional, client_id in IDENTITY_SYNC_AUDIENCE_CLIENTS, client_id)
        for client_id in IDENTITY_SYNC_AUDIENCE_CLIENTS:
            self.assertTrue(self.clients[client_id]["serviceAccountsEnabled"], client_id)


def _authorize(client_id: str, redirect_uri: str, **extra) -> object:
    query = urllib.parse.urlencode({"client_id": client_id, "response_type": "code", "scope": "openid",
                                    "state": "s", "nonce": "n", "redirect_uri": redirect_uri, **extra})
    return get_without_redirect(f"{ortam('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{query}")


def _assert_refused_without_pkce(test: unittest.TestCase, response) -> None:
    location = response.basliklar.get("Location", "")
    test.assertFalse(b'name="username"' in response.govde, safe_detail(response))
    test.assertNotIn("code=", location)
    if response.durum in (302, 303):
        test.assertIn("error=invalid_request", location)
    else:
        test.assertEqual(response.durum, 400)


def _audiences(claims: dict) -> list:
    aud = claims.get("aud", [])
    return [aud] if isinstance(aud, str) else list(aud)


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL is not set; live Keycloak test skipped")
class RealmBacklogLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_token = yonetici_belirteci()
        cls.realm = admin("", cls.admin_token).json()

    def test_resolved_values_come_from_the_environment(self):
        self.assertEqual(self.realm["displayName"], ortam("IDENTITY_BRAND_NAME"))
        self.assertEqual(self.realm["sslRequired"], ortam("ATONOTA_SSL_REQUIRED"))
        smtp = self.realm["smtpServer"]
        self.assertEqual(smtp["auth"], ortam("ATONOTA_SMTP_AUTH"))
        self.assertEqual(smtp["starttls"], ortam("ATONOTA_SMTP_STARTTLS"))
        self.assertEqual(smtp["fromDisplayName"], ortam("IDENTITY_BRAND_NAME"))
        self.assertNotIn("${", str(smtp))

    def test_mobile_client_refuses_login_without_pkce(self):
        _assert_refused_without_pkce(self, _authorize("mobile-app", ortam("ATONOTA_MOBILE_REDIRECT_URI")))

    def test_mobile_client_opens_login_with_pkce(self):
        _, challenge = pkce_pair()
        response = _authorize("mobile-app", ortam("ATONOTA_MOBILE_REDIRECT_URI"),
                              code_challenge=challenge, code_challenge_method="S256")
        self.assertEqual(response.durum, 200, response.basliklar.get("Location"))
        self.assertTrue(b'name="username"' in response.govde, safe_detail(response))

    def test_mobile_client_refuses_a_plain_challenge(self):
        response = _authorize("mobile-app", ortam("ATONOTA_MOBILE_REDIRECT_URI"),
                              code_challenge="a" * 43, code_challenge_method="plain")
        _assert_refused_without_pkce(self, response)

    def test_mobile_client_has_no_password_or_client_credentials_grant(self):
        token_url = f"{ortam('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/token"
        password = istek("POST", token_url, form={"grant_type": "password", "client_id": "mobile-app",
                                                  "username": "nobody@example.test", "password": "x"})
        self.assertIn(password.durum, (400, 401), safe_detail(password))
        self.assertTrue(password.json().get("error") in ("unauthorized_client", "invalid_client"), safe_detail(password))
        service = istek("POST", token_url, form={"grant_type": "client_credentials", "client_id": "mobile-app"})
        self.assertIn(service.durum, (400, 401), safe_detail(service))

    def test_press_client_refuses_login_without_pkce(self):
        redirect = f"{ortam('ATONOTA_PRESS_URL')}/api/method/press_tr.api.auth.keycloak_callback"
        _assert_refused_without_pkce(self, _authorize("press", redirect))

    def test_tenant_service_client_gets_identity_sync_audience(self):
        response = istemci_belirteci("site-kiraci1", ortam("ATONOTA_SITE_KIRACI1_SECRET"), "aud-identity-sync")
        self.assertEqual(response.durum, 200, safe_detail(response))
        claims = jwt_govdesi(response.json()["access_token"])
        self.assertEqual(claims["aud"], "identity-sync")
        self.assertEqual(claims["azp"], "site-kiraci1")
        self.assertNotIn("realm_access", claims)
        self.assertNotIn("resource_access", claims)

    def test_press_service_gets_identity_sync_audience(self):
        response = istemci_belirteci("press-service", ortam("ATONOTA_PRESS_SERVICE_SECRET"), "aud-identity-sync")
        self.assertEqual(response.durum, 200, safe_detail(response))
        claims = jwt_govdesi(response.json()["access_token"])
        self.assertEqual(claims["aud"], "identity-sync")
        self.assertEqual(claims["azp"], "press-service")

    def test_tenant_service_token_without_scope_has_no_identity_sync_audience(self):
        response = istemci_belirteci("site-kiraci1", ortam("ATONOTA_SITE_KIRACI1_SECRET"))
        self.assertEqual(response.durum, 200, safe_detail(response))
        self.assertNotIn("identity-sync", _audiences(jwt_govdesi(response.json()["access_token"])))

    def test_other_clients_cannot_get_identity_sync_audience(self):
        for client_id, secret in (("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET"),
                                  ("press", "ATONOTA_PRESS_SECRET")):
            response = istemci_belirteci(client_id, ortam(secret), "aud-identity-sync")
            # identity-sync has a service account: the scope is refused. press is a browser client
            # without client credentials grant: the grant is refused first.
            expected = "HTTP 400 invalid_scope" if client_id == "identity-sync" else "HTTP 401 unauthorized_client"
            self.assertEqual(safe_detail(response), expected, client_id)


if __name__ == "__main__":
    unittest.main()
