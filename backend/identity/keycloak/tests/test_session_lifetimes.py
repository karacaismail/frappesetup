"""Gap backlog item 6: Karar 19 session lifetimes (project record O-25).

Employee (tenant clients site-kiraci1 and mobile-app): 1 hour idle, 24 hours in total. After the level of
authentication is older than 1 hour, an open Keycloak cookie does not skip the login.
Customer (press): 7 days idle, 30 days in total, from the realm settings.

Mechanism, verified in Keycloak 26.8.2 source: the tenant clients request ACR "employee" (LoA 1) through
default.acr.values and minimum.acr.value. The browser flow has a "conditional-level-of-authentication"
condition with loa-max-age 3600. CookieAuthenticator only finishes the login when the requested level is
still valid (AcrStore.getHighestAuthenticatedLevelFromPreviousAuthentication); otherwise the condition
runs the login steps again (ConditionalLoaAuthenticator.matchCondition).
"""

from __future__ import annotations

import json
import time
import unittest
import urllib.parse

from test_account_backlog import _login, _pause
from test_eklentiler import _ac
from yardimci import admin, canli_var_mi, ortam, realm_oku, tenant_authorize_url, yonetici_belirteci

HOUR = 3600
DAY = 24 * HOUR
EMPLOYEE_CLIENTS = ("site-kiraci1", "mobile-app")
LOA_CONFIG = "atonota-employee-loa"


def _flows(realm: dict) -> dict:
    return {f["alias"]: f for f in realm["authenticationFlows"]}


class SessionLifetimeFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.clients = {c["clientId"]: c for c in cls.realm["clients"]}

    def test_customer_lifetimes_are_the_realm_lifetimes(self):
        self.assertEqual(self.realm["ssoSessionIdleTimeout"], 7 * DAY)
        self.assertEqual(self.realm["ssoSessionMaxLifespan"], 30 * DAY)
        self.assertEqual(self.realm["accessTokenLifespan"], 5 * 60)
        press = self.clients["press"]["attributes"]
        for key in ("client.session.idle.timeout", "client.session.max.lifespan", "default.acr.values"):
            self.assertNotIn(key, press, key)

    def test_employee_clients_have_one_hour_idle_and_one_day_total(self):
        for client_id in EMPLOYEE_CLIENTS:
            attributes = self.clients[client_id]["attributes"]
            self.assertEqual(attributes["client.session.idle.timeout"], str(HOUR), client_id)
            self.assertEqual(attributes["client.session.max.lifespan"], str(DAY), client_id)

    def test_employee_clients_request_the_employee_level(self):
        for client_id in EMPLOYEE_CLIENTS:
            attributes = self.clients[client_id]["attributes"]
            self.assertEqual(json.loads(attributes["acr.loa.map"]), {"employee": 1}, client_id)
            self.assertEqual(attributes["default.acr.values"], "employee", client_id)
            self.assertEqual(attributes["minimum.acr.value"], "employee", client_id)

    def test_browser_flow_has_the_level_condition_around_every_login_method(self):
        flows = _flows(self.realm)
        login = flows["atonota-browser-giris"]["authenticationExecutions"]
        self.assertEqual(len(login), 1)
        self.assertEqual(login[0]["requirement"], "CONDITIONAL")
        level_flow = flows[login[0]["flowAlias"]]["authenticationExecutions"]
        condition = level_flow[0]
        self.assertEqual(condition["authenticator"], "conditional-level-of-authentication")
        self.assertEqual(condition["requirement"], "REQUIRED")
        self.assertEqual(condition["authenticatorConfig"], LOA_CONFIG)
        methods = flows[level_flow[1]["flowAlias"]]["authenticationExecutions"]
        self.assertEqual(level_flow[1]["requirement"], "REQUIRED")
        self.assertEqual({m["flowAlias"] for m in methods}, {"atonota-browser-parola", "atonota-browser-magic-link"})
        config = {c["alias"]: c for c in self.realm["authenticatorConfig"]}[LOA_CONFIG]["config"]
        self.assertEqual(config["loa-condition-level"], "1")
        self.assertEqual(config["loa-max-age"], str(HOUR))

    def test_the_cookie_step_stays_first(self):
        top = _flows(self.realm)[self.realm["browserFlow"]]["authenticationExecutions"]
        self.assertEqual(top[0]["authenticator"], "auth-cookie")


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL is not set; live Keycloak test skipped")
class SessionLifetimeLiveTest(unittest.TestCase):
    """Shortens the level's max age to 5 seconds for the test and puts 3600 back afterwards."""

    SHORT = 5

    def setUp(self):
        self.admin_token = yonetici_belirteci()
        executions = admin("/authentication/flows/atonota-browser-giris/executions", self.admin_token).json()
        condition = next(e for e in executions if e.get("providerId") == "conditional-level-of-authentication")
        self.config_id = condition["authenticationConfig"]
        config = admin(f"/authentication/config/{self.config_id}", self.admin_token).json()
        self.original = dict(config)
        config["config"] = {**config["config"], "loa-max-age": str(self.SHORT)}
        self.assertEqual(admin(f"/authentication/config/{self.config_id}", self.admin_token, "PUT", config).durum, 204)
        self.addCleanup(self._restore)
        user = admin("/users?email=totp.ornek@example.test&exact=true", self.admin_token).json()[0]
        admin(f"/attack-detection/brute-force/users/{user['id']}", self.admin_token, yontem="DELETE")

    def _restore(self):
        token = yonetici_belirteci()
        admin(f"/authentication/config/{self.config_id}", token, "PUT", self.original)

    def _press_authorize_url(self, **extra) -> str:
        from yardimci import pkce_pair
        _, challenge = pkce_pair()
        query = urllib.parse.urlencode({**extra,
            "client_id": "press", "response_type": "code", "scope": "openid", "state": "s", "nonce": "n",
            "redirect_uri": f"{ortam('ATONOTA_PRESS_URL')}/api/method/press_tr.api.auth.keycloak_callback",
            "code_challenge": challenge, "code_challenge_method": "S256"})
        return f"{ortam('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{query}"

    def test_cookie_finishes_the_login_while_the_level_is_valid(self):
        opener, status, headers, _ = _login(tenant_authorize_url())
        self.assertEqual(status, 302)
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")
        status, headers, _ = _ac(opener, tenant_authorize_url())
        self.assertEqual(status, 302, "a valid level lets the cookie finish the login")
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")

    def test_employee_must_log_in_again_after_the_level_expires(self):
        opener, status, headers, _ = _login(tenant_authorize_url())
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")
        time.sleep(self.SHORT + 2)
        status, headers, html = _ac(opener, tenant_authorize_url())
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
        self.assertEqual(status, 200)
        self.assertTrue('name="password"' in html, f"HTTP {status}")

    def test_a_lower_requested_level_does_not_skip_the_login(self):
        # minimum.acr.value=employee: acr_values=0 or an unknown ACR must not let the cookie answer after expiry.
        opener, status, headers, _ = _login(tenant_authorize_url())
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")
        time.sleep(self.SHORT + 2)
        for extra in ("&acr_values=0", "&acr_values=unknown"):
            with self.subTest(extra=extra):
                status, headers, html = _ac(opener, tenant_authorize_url() + extra)
                self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")

    def test_customer_cookie_is_not_affected(self):
        opener, status, headers, _ = _login(tenant_authorize_url())
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")
        time.sleep(self.SHORT + 2)
        _pause()
        status, headers, _ = _ac(opener, self._press_authorize_url())
        self.assertEqual(status, 302, "the customer client requests no level, so the 7 day cookie is enough")
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")


    def test_press_can_force_a_fresh_login(self):
        # Contract 42f8e32: before an account deletion Press asks Keycloak for a fresh login
        # (prompt=login, max_age=0). The open cookie must not answer either request.
        opener, status, headers, _ = _login(tenant_authorize_url())
        self.assertTrue("code=" in headers["Location"], f"HTTP {status}")
        status, headers, _ = _ac(opener, self._press_authorize_url())
        self.assertTrue("code=" in headers.get("Location", ""), f"HTTP {status}")
        # OIDCLoginProtocol.requireReauthentication (26.8.2, line 570) asks again only when
        # auth_time + max_age < now, counted in whole seconds. A max_age=0 request in the same second as the
        # login is answered by the cookie. prompt=login always asks again. Press sends both parameters.
        time.sleep(2)
        for extra in ({"prompt": "login"}, {"max_age": "0"}, {"prompt": "login", "max_age": "0"}):
            with self.subTest(**extra):
                status, headers, html = _ac(opener, self._press_authorize_url(**extra))
                self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
                self.assertEqual(status, 200)
                self.assertTrue('name="password"' in html, f"HTTP {status}")

if __name__ == "__main__":
    unittest.main()
