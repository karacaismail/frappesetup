"""Gap backlog items 7, 8 and 11 (backend/docs/gap-backlog.md, kimlik-realm).

7: an old refresh token is refused (contract section 2: the refresh token changes on every use).
8: the passkey registration step is enabled; disabled providers are not shown on the login page.
11: account deletion starts in Press, identity-sync deletes the Keycloak user last (contract 42f8e32).
    Keycloak's own delete_account action stays disabled and nobody gets the delete-account role.
"""

from __future__ import annotations

import time
import unittest
import urllib.parse
import uuid

from test_eklentiler import _ac, _cerezli_acici, _form_hedefi
from test_second_factor import TOTP_PASSWORD, TOTP_USER, fresh_totp_code
from yardimci import (admin, canli_var_mi, istek, ortam, realm_oku, tenant_authorize_url, tenant_authorize_with_pkce,
                      tenant_callback_url, yonetici_belirteci)

REQUIRED_ON = {"CONFIGURE_TOTP", "UPDATE_PASSWORD", "VERIFY_EMAIL", "webauthn-register",
               "webauthn-register-passwordless"}


class AccountBacklogFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.actions = {a["alias"]: a for a in cls.realm.get("requiredActions", [])}

    def test_required_actions_are_listed_and_enabled(self):
        for alias in REQUIRED_ON:
            self.assertIn(alias, self.actions, alias)
            self.assertTrue(self.actions[alias]["enabled"], alias)

    def test_no_required_action_is_forced_on_every_new_user(self):
        # A default action would run for invited employees too. Keycloak asks for TOTP and e-mail by policy.
        self.assertFalse(self.actions["webauthn-register-passwordless"]["defaultAction"])

    def test_keycloak_delete_account_action_is_disabled(self):
        # Contract 42f8e32: the action deletes the user in its first step, before Press and the tenants.
        self.assertFalse(self.actions["delete_account"]["enabled"])
        self.assertFalse(self.actions["delete_account"]["defaultAction"])

    def test_disabled_providers_are_hidden(self):
        for provider in self.realm["identityProviders"]:
            if not provider["enabled"]:
                self.assertTrue(provider["hideOnLogin"], provider["alias"])

    def test_no_role_grants_delete_account(self):
        default_role = self.realm["defaultRole"]["name"]
        role = next(r for r in self.realm["roles"]["realm"] if r["name"] == default_role)
        # Keycloak's own default composites stay; delete-account is not among them.
        self.assertEqual(set(role["composites"]["client"]["account"]), {"view-profile", "manage-account"})
        self.assertTrue({"offline_access", "uma_authorization"} <= set(role["composites"]["realm"]))
        for realm_role in self.realm["roles"]["realm"]:
            account = realm_role.get("composites", {}).get("client", {}).get("account", [])
            self.assertNotIn("delete-account", account, realm_role["name"])
        self.assertNotIn("employee", {r["name"] for r in self.realm["roles"]["realm"]})

    def test_refresh_token_changes_on_every_use(self):
        self.assertTrue(self.realm["revokeRefreshToken"])
        self.assertEqual(self.realm["refreshTokenMaxReuse"], 0)


def _pause():
    # Two login attempts within one second lock the user (quickLoginCheckMilliSeconds).
    time.sleep(1.2)


def _login(authorize_url: str):
    """Logs the TOTP sample user in and returns (opener, final headers)."""
    opener = _cerezli_acici()
    _, _, html = _ac(opener, authorize_url)
    form = urllib.parse.urlencode({"username": TOTP_USER, "password": TOTP_PASSWORD, "credentialId": ""}).encode()
    _, _, html = _ac(opener, _form_hedefi(html), form)
    _pause()
    status, headers, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
    if status == 200 and 'name="otp"' in html:
        # Keycloak refused a code that an earlier run had already used. Wait for the next period once.
        time.sleep(30 - time.time() % 30 + 1)
        status, headers, html = _ac(opener, _form_hedefi(html),
                                    urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
    return opener, status, headers, html


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL yok, canlı Keycloak testi atlandı")
class AccountBacklogLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.admin_token = yonetici_belirteci()
        cls.token_url = f"{cls.kc}/realms/platform/protocol/openid-connect/token"

    def setUp(self):
        self.admin_token = yonetici_belirteci()  # the master admin token lives 60 seconds
        user = admin(f"/users?email={TOTP_USER}&exact=true", self.admin_token).json()[0]
        admin(f"/attack-detection/brute-force/users/{user['id']}", self.admin_token, yontem="DELETE")

    def _refresh(self, refresh_token: str):
        return istek("POST", self.token_url, form={
            "grant_type": "refresh_token", "client_id": "site-kiraci1",
            "client_secret": ortam("ATONOTA_SITE_KIRACI1_SECRET"), "refresh_token": refresh_token})

    def test_old_refresh_token_is_refused(self):
        url, verifier = tenant_authorize_with_pkce()
        _, status, headers, _ = _login(url)
        self.assertEqual(status, 302)
        code = urllib.parse.parse_qs(urllib.parse.urlsplit(headers["Location"]).query)["code"][0]
        tokens = istek("POST", self.token_url, form={
            "grant_type": "authorization_code", "client_id": "site-kiraci1",
            "client_secret": ortam("ATONOTA_SITE_KIRACI1_SECRET"), "redirect_uri": tenant_callback_url(),
            "code": code, "code_verifier": verifier}).json()
        first = tokens["refresh_token"]
        second = self._refresh(first)
        self.assertEqual(second.durum, 200, second.govde[:200])
        self.assertNotEqual(second.json()["refresh_token"], first)
        reused = self._refresh(first)
        self.assertEqual(reused.durum, 400, reused.govde[:200])
        self.assertEqual(reused.json()["error"], "invalid_grant")

    def test_passkey_registration_step_is_enabled(self):
        actions = {a["alias"]: a for a in admin("/authentication/required-actions", self.admin_token).json()}
        for alias in REQUIRED_ON:
            self.assertTrue(actions[alias]["enabled"], alias)

    def test_disabled_providers_are_not_on_the_login_page(self):
        _, _, html = _ac(_cerezli_acici(), tenant_authorize_url())
        for alias in ("google", "apple"):
            self.assertNotIn(f"/broker/{alias}/login", html, alias)
            self.assertNotIn(f'id="social-{alias}"', html, alias)

    def test_new_user_does_not_get_the_delete_account_role(self):
        username = f"customer-{uuid.uuid4().hex[:10]}"
        created = admin("/users", self.admin_token, "POST",
                        {"username": username, "email": f"{username}@example.test", "enabled": True})
        self.assertEqual(created.durum, 201, created.govde[:200])
        user_id = created.basliklar["Location"].rstrip("/").rsplit("/", 1)[1]
        self.addCleanup(admin, f"/users/{user_id}", self.admin_token, "DELETE")
        account = admin("/clients?clientId=account", self.admin_token).json()[0]["id"]
        roles = {r["name"] for r in admin(
            f"/users/{user_id}/role-mappings/clients/{account}/composite", self.admin_token).json()}
        self.assertNotIn("delete-account", roles)
        self.assertIn("manage-account", roles)

    def test_keycloak_delete_account_action_is_off_live(self):
        actions = {a["alias"]: a for a in admin("/authentication/required-actions", self.admin_token).json()}
        self.assertFalse(actions["delete_account"]["enabled"])

    def test_delete_step_does_not_delete_the_user(self):
        # A throwaway customer without a second factor, so the test does not share TOTP codes.
        import secrets

        username = f"customer-{uuid.uuid4().hex[:10]}"
        password = "Musteri-" + secrets.token_urlsafe(12)
        created = admin("/users", self.admin_token, "POST", {
            "username": username, "email": f"{username}@example.test", "emailVerified": True,
            "firstName": "Deneme", "lastName": "Musteri", "enabled": True,
            "credentials": [{"type": "password", "value": password, "temporary": False}]})
        self.assertEqual(created.durum, 201, created.govde[:200])
        user_id = created.basliklar["Location"].rstrip("/").rsplit("/", 1)[1]
        self.addCleanup(admin, f"/users/{user_id}", self.admin_token, "DELETE")

        opener = _cerezli_acici()
        _, _, html = _ac(opener, tenant_authorize_url() + "&kc_action=delete_account")
        form = urllib.parse.urlencode({"username": f"{username}@example.test", "password": password,
                                       "credentialId": ""}).encode()
        status, headers, html = _ac(opener, _form_hedefi(html), form)
        location = headers.get("Location", "")
        if status in (302, 303) and location.startswith(self.kc):
            status, headers, html = _ac(opener, location)
        self.assertNotIn('id="kc-deleteaccount-form"', html, "Keycloak must not offer its own delete step")
        self.assertEqual(admin(f"/users/{user_id}", yonetici_belirteci()).durum, 200, "the user must still exist")


if __name__ == "__main__":
    unittest.main()
