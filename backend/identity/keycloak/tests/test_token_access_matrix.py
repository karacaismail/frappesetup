"""D-6: exercise token targets, scopes and roles through live Keycloak endpoints."""

from __future__ import annotations

import unittest
import urllib.parse

from test_account_backlog import _login
from test_eklentiler import _ac
from test_second_factor import TOTP_USER
from yardimci import (
    admin,
    canli_var_mi,
    get_without_redirect,
    istek,
    istemci_belirteci,
    jwt_govdesi,
    ortam,
    pkce_pair,
    safe_detail,
    tenant_callback_url,
    yonetici_belirteci,
)

TARGET_SCOPES = {
    "aud-site-kiraci1": "site-kiraci1",
    "aud-press": "press",
    "aud-mobile-app": "mobile-app",
    "aud-identity-sync": "identity-sync",
}
ADMIN_SCOPES = {"admin-api", "kc-admin-api"}
MANAGEMENT_ROLES = {
    "view-users",
    "query-users",
    "manage-users",
    "view-organizations",
    "manage-organizations",
    "query-groups",  # Keycloak composite of view-users
    "query-organizations",  # Keycloak composite of view-organizations
}


def audiences(claims: dict) -> set[str]:
    value = claims.get("aud", [])
    return {value} if isinstance(value, str) else set(value)


@unittest.skipUnless(canli_var_mi(), "Keycloak development environment is required")
class TokenAccessMatrixTest(unittest.TestCase):
    def setUp(self):
        self.keycloak_url = ortam("KC_PUBLIC_URL")
        self.issuer = f"{self.keycloak_url}/realms/platform"
        self.token_url = f"{self.issuer}/protocol/openid-connect/token"
        self.management_audiences = {"realm-management", f"{self.keycloak_url}/admin/realms/platform"}

    def assert_client_claims(self, claims, client_id, expected_audience, *, scopes, roles=()):
        self.assertEqual(claims.get("azp"), client_id)
        self.assertEqual(audiences(claims), set(expected_audience))
        self.assertEqual(set(claims.get("scope", "").split()) & (TARGET_SCOPES.keys() | ADMIN_SCOPES), set(scopes))
        resource_roles = claims.get("resource_access", {})
        self.assertEqual(set(resource_roles.get("realm-management", {}).get("roles", [])), set(roles))
        self.assertFalse(claims.get("realm_access", {}).get("roles"))

    def test_service_grant_targets_scopes_and_roles(self):
        service_clients = {
            "site-kiraci1": ("ATONOTA_SITE_KIRACI1_SECRET", {"aud-identity-sync"}),
            "press-service": ("ATONOTA_PRESS_SERVICE_SECRET", {"aud-site-kiraci1", "aud-identity-sync"}),
            "identity-sync": ("ATONOTA_IDENTITY_SYNC_SECRET", {"aud-site-kiraci1", "aud-press"}),
        }
        for client_id, (secret_name, allowed) in service_clients.items():
            secret = ortam(secret_name)
            for scope in (None, *TARGET_SCOPES, "admin-api kc-admin-api"):
                with self.subTest(client=client_id, scope=scope):
                    response = istemci_belirteci(client_id, secret, scope)
                    if scope is None:
                        expected = set()
                        scopes = set()
                        roles = set()
                    elif scope in allowed:
                        expected = {TARGET_SCOPES[scope]}
                        # Audience scopes set aud but are intentionally omitted from the scope claim.
                        scopes = set()
                        roles = set()
                    elif client_id == "identity-sync" and scope == "admin-api kc-admin-api":
                        expected = self.management_audiences
                        scopes = {"kc-admin-api"}
                        roles = MANAGEMENT_ROLES
                    else:
                        self.assertEqual(safe_detail(response), "HTTP 400 invalid_scope")
                        continue
                    self.assertEqual(response.durum, 200, safe_detail(response))
                    claims = jwt_govdesi(response.json()["access_token"])
                    self.assert_client_claims(claims, client_id, expected, scopes=scopes, roles=roles)
                    management_response = admin("/users?max=1", response.json()["access_token"])
                    expected_status = (200,) if roles else (401, 403)
                    self.assertIn(management_response.durum, expected_status, safe_detail(management_response))

    def test_service_grants_cannot_combine_target_boundaries(self):
        combinations = (
            ("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-site-kiraci1 aud-press"),
            ("identity-sync", "ATONOTA_IDENTITY_SYNC_SECRET", "aud-site-kiraci1 admin-api kc-admin-api"),
            ("press-service", "ATONOTA_PRESS_SERVICE_SECRET", "aud-site-kiraci1 aud-identity-sync"),
        )
        for client_id, secret_name, scope in combinations:
            with self.subTest(client=client_id, scope=scope):
                response = istemci_belirteci(client_id, ortam(secret_name), scope)
                if response.durum != 200:
                    self.assertEqual(safe_detail(response), "HTTP 400 invalid_scope")
                    continue
                claims = jwt_govdesi(response.json()["access_token"])
                actual = audiences(claims)
                if ADMIN_SCOPES <= set(scope.split()) and actual == self.management_audiences:
                    self.assert_client_claims(
                        claims, client_id, actual, scopes={"kc-admin-api"}, roles=MANAGEMENT_ROLES
                    )
                    continue
                allowed = {TARGET_SCOPES[name] for name in scope.split() if name in TARGET_SCOPES}
                self.assertTrue(len(actual) == 1 and actual <= allowed, f"HTTP 200 with audiences {sorted(actual)}")
                self.assert_client_claims(claims, client_id, actual, scopes=set())

    def test_browser_only_clients_cannot_obtain_service_tokens(self):
        for client_id in ("press", "mobile-app"):
            _, secret = self.browser_clients()[client_id]
            for scope in (None, *TARGET_SCOPES):
                with self.subTest(client=client_id, scope=scope):
                    form = {"grant_type": "client_credentials", "client_id": client_id}
                    if secret is not None:
                        form["client_secret"] = secret
                    if scope is not None:
                        form["scope"] = scope
                    response = istek("POST", self.token_url, form=form)
                    self.assertIn(response.durum, (400, 401), safe_detail(response))

    def browser_clients(self):
        return {
            "site-kiraci1": (tenant_callback_url(), ortam("ATONOTA_SITE_KIRACI1_SECRET")),
            "press": (
                f"{ortam('ATONOTA_PRESS_URL')}/api/method/press_tr.api.auth.keycloak_callback",
                ortam("ATONOTA_PRESS_SECRET"),
            ),
            "mobile-app": (ortam("ATONOTA_MOBILE_REDIRECT_URI"), None),
        }

    def authorize(self, client_id, callback, scope):
        verifier, challenge = pkce_pair()
        query = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": callback,
                "response_type": "code",
                "scope": scope,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "matrix-test",
                "nonce": "matrix-test",
            }
        )
        return f"{self.issuer}/protocol/openid-connect/auth?{query}", verifier

    def test_browser_clients_reject_foreign_audience_scopes(self):
        for client_id, (callback, _) in self.browser_clients().items():
            for scope, target in TARGET_SCOPES.items():
                if target == client_id or (client_id, target) == ("site-kiraci1", "identity-sync"):
                    continue  # test the service-only scope at the token endpoint below
                with self.subTest(client=client_id, target=target):
                    url, _ = self.authorize(client_id, callback, f"openid {scope}")
                    response = get_without_redirect(url)
                    location = response.basliklar.get("Location", "")
                    error = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query).get("error")
                    self.assertTrue(error == ["invalid_scope"], safe_detail(response))

    def open_tenant_session(self):
        clients = self.browser_clients()
        token = yonetici_belirteci()
        user = admin(f"/users?email={TOTP_USER}&exact=true", token).json()[0]
        admin(f"/attack-detection/brute-force/users/{user['id']}", token, yontem="DELETE")
        tenant_url, _ = self.authorize("site-kiraci1", clients["site-kiraci1"][0], "openid")
        opener, status, _, _ = _login(tenant_url)
        self.assertEqual(status, 302)
        return opener

    def browser_token(self, opener, client_id, scope):
        callback, secret = self.browser_clients()[client_id]
        url, verifier = self.authorize(client_id, callback, scope)
        status, headers, _ = _ac(opener, url)
        self.assertEqual(status, 302)
        location = headers.get("Location", "")
        parameters = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)
        if parameters.get("error") == ["invalid_scope"]:
            return None
        code = parameters.get("code")
        self.assertTrue(bool(code), f"HTTP {status}")
        form = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": callback,
            "code_verifier": verifier,
            "code": code[0],
        }
        if secret:
            form["client_secret"] = secret
        response = istek("POST", self.token_url, form=form)
        if safe_detail(response) == "HTTP 400 invalid_scope":
            return None
        self.assertEqual(response.durum, 200, safe_detail(response))
        return response.json()

    def test_browser_code_exchange_binds_id_token_to_the_requesting_client(self):
        opener = self.open_tenant_session()
        for client_id in self.browser_clients():
            with self.subTest(client=client_id):
                tokens = self.browser_token(opener, client_id, "openid")
                self.assertIsNotNone(tokens)
                self.assert_client_claims(
                    jwt_govdesi(tokens["id_token"]),
                    client_id,
                    {client_id},
                    scopes=set(),
                )
                self.assert_client_claims(jwt_govdesi(tokens["access_token"]), client_id, set(), scopes=set())

    def test_tenant_browser_cannot_get_identity_sync_service_audience(self):
        tokens = self.browser_token(self.open_tenant_session(), "site-kiraci1", "openid aud-identity-sync")
        if tokens is not None:
            claims = jwt_govdesi(tokens["access_token"])
            self.assert_client_claims(claims, "site-kiraci1", set(), scopes=set())
