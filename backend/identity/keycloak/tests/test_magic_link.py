"""Magic link as a step inside the browser flow (owner decision, second review follow-up).

Conditions under test:
1. The link is a flow step. After the click the flow continues and the second factor is not skipped.
2. The link is bound to the login request and the browser session. Another browser cannot log in with it.
3. Short life (at most 300 s), single use, and a mail preview must not consume the link (mobile MT-7).
4. No REST endpoint issues links. The extension's REST resource is disabled and answers 404.
Expected values come from docs/sozlesmeler.md section 2, docs/kararlar/0003-keycloak-eklentileri.md and MT-7.
"""

from __future__ import annotations

import re
import time
import unittest
import urllib.parse

from test_eklentiler import AKIS, _ac, _cerezli_acici, _form_hedefi, _keycloak_icinde_izle
from test_second_factor import TOTP_SECRET, TOTP_USER, fresh_totp_code
from yardimci import KLASOR, admin, canli_var_mi, istek, ortam, realm_oku, tenant_authorize_url, yonetici_belirteci

MAGIC_LINK = "magiclink"
MAGIC_LINK_CONTINUATION = "magiclink-continuation"
MAGIC_LINK_REST_PATH = "magiclink-login"
MAGIC_LINK_CONFIG = "atonota-sihirli-baglanti"
MAX_LIFETIME = 300
PINNED_COMMIT = "7b4ee949a39a7ee953987162479ae1da2c57c3cb"
PLAIN_USER = "ayse.ornek@example.test"
OTHER_USER = "mehmet.ornek@example.test"


class MagicLinkFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = realm_oku()
        cls.dockerfile = (KLASOR / "Dockerfile").read_text(encoding="utf-8")
        cls.compose = (KLASOR.parents[1] / "dev" / "compose.keycloak.yaml").read_text(encoding="utf-8")
        cls.flows = {f["alias"]: f for f in cls.realm["authenticationFlows"]}
        cls.executions = [e for f in cls.realm["authenticationFlows"] for e in f["authenticationExecutions"]]

    def test_extension_is_built_from_pinned_source_with_checksum(self):
        # License Apache-2.0 verified in the repository LICENSE file; the source archive is pinned by commit and SHA-256.
        self.assertIn(f"ARG MAGICLINK_COMMIT={PINNED_COMMIT}", self.dockerfile)
        self.assertIn("cloudflightio/keycloak-magic-link/archive/${MAGICLINK_COMMIT}.tar.gz", self.dockerfile)
        self.assertRegex(self.dockerfile, r"--checksum=sha256:[0-9a-f]{64} \\\n\s+https://github.com/cloudflightio/keycloak-magic-link/archive")
        self.assertIn("-Dkeycloak.version=26.8.2", self.dockerfile)

    def test_magic_link_is_a_flow_step_followed_by_second_factor(self):
        steps = [e for e in self.executions if e.get("authenticator") == MAGIC_LINK]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["requirement"], "REQUIRED")
        self.assertEqual(steps[0]["authenticatorConfig"], MAGIC_LINK_CONFIG)
        parent = [f for f in self.realm["authenticationFlows"] if steps[0] in f["authenticationExecutions"]][0]
        after = [e for e in parent["authenticationExecutions"] if e["priority"] > steps[0]["priority"]]
        self.assertTrue(after and after[0]["authenticatorFlow"] and after[0]["requirement"] == "CONDITIONAL")
        second = self.flows[after[0]["flowAlias"]]["authenticationExecutions"]
        self.assertIn("conditional-user-configured", [e.get("authenticator") for e in second])
        self.assertIn("auth-otp-form", [e.get("authenticator") for e in second])
        self.assertNotIn(MAGIC_LINK_CONTINUATION, [e.get("authenticator") for e in self.executions])

    def test_magic_link_lifetime_is_short(self):
        config = {c["alias"]: c["config"] for c in self.realm["authenticatorConfig"]}[MAGIC_LINK_CONFIG]
        self.assertLessEqual(int(config["magickey.validity.duration"]), MAX_LIFETIME)

    def test_rest_resource_and_continuation_are_disabled_in_compose(self):
        self.assertIn("KC_SPI_REALM_RESTAPI_EXTENSION__MAGICLINK_LOGIN__ENABLED", self.compose)
        self.assertIn("KC_SPI_AUTHENTICATOR__MAGICLINK_CONTINUATION__ENABLED", self.compose)


def _magic_link_execution_id(admin_token: str) -> str:
    executions = admin(f"/authentication/flows/{AKIS}/executions", admin_token).json()
    return [e["id"] for e in executions if e.get("providerId") == MAGIC_LINK][0]


class Mailpit:
    def __init__(self, base: str):
        self.base = base

    def clear(self):
        istek("DELETE", f"{self.base}/api/v1/messages")

    def latest_link(self, recipient: str, wait_seconds: int = 20) -> str:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            for message in istek("GET", f"{self.base}/api/v1/messages").json().get("messages", []):
                if any(a.get("Address") == recipient for a in message.get("To", [])):
                    detail = istek("GET", f"{self.base}/api/v1/message/{message['ID']}").json()
                    text = (detail.get("Text") or "") + " " + (detail.get("HTML") or "")
                    found = re.search(r"https?://[^\s\"'<>]+login-actions/authenticate[^\s\"'<>]+magickey=[^\s\"'<>]+", text)
                    if found:
                        return found.group(0).replace("&amp;", "&")
            time.sleep(1)
        raise AssertionError(f"no magic link mail for {recipient}")


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL missing, live Keycloak test skipped")
class MagicLinkLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.admin_token = yonetici_belirteci()
        cls.mailpit = Mailpit(f"http://127.0.0.1:{ortam('MAILPIT_UI_PORT')}")
        cls.execution_id = _magic_link_execution_id(cls.admin_token)

    def _request_link(self, email: str):
        """Opens the login page, switches to the magic link step and submits the e-mail address."""
        self.mailpit.clear()
        opener = _cerezli_acici()
        status, _, html = _ac(opener, tenant_authorize_url())
        self.assertEqual(status, 200)
        self.assertTrue("tryAnotherWay" in html, "login page must offer another way")
        status, _, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"tryAnotherWay": "on"}).encode())
        status, _, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"authenticationExecution": self.execution_id}).encode())
        self.assertEqual(status, 200)
        self.assertTrue('name="username"' in html and 'name="password"' not in html, "e-mail form expected")
        status, _, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"username": email}).encode())
        self.assertEqual(status, 200)
        return opener, self.mailpit.latest_link(email)

    def test_link_logs_in_only_in_the_requesting_browser_and_only_once(self):
        opener, link = self._request_link(PLAIN_USER)
        # MT-7: a preview or scanner without the browser session must not consume the link.
        stranger = _cerezli_acici()
        status, headers, _ = _keycloak_icinde_izle(stranger, link, self.kc)
        self.assertNotIn("code=", headers.get("Location", ""), "another browser must not get a code")
        # The requesting browser still completes the login.
        status, headers, _ = _keycloak_icinde_izle(opener, link, self.kc)
        location = headers.get("Location", "")
        self.assertEqual(status, 302, "first click in the requesting browser must finish the login")
        self.assertTrue(location.startswith(ortam("ATONOTA_SITE_KIRACI1_URL")), location[:120])
        self.assertIn("code=", location)
        # Single use: the same link does not work twice.
        status, headers, _ = _keycloak_icinde_izle(opener, link, self.kc)
        self.assertNotIn("code=", headers.get("Location", ""), "link must be single use")

    def test_link_does_not_skip_totp(self):
        opener, link = self._request_link(TOTP_USER)
        status, headers, html = _keycloak_icinde_izle(opener, link, self.kc)
        self.assertNotIn("code=", headers.get("Location", ""), "no code before the second factor")
        self.assertTrue('name="otp"' in html, "the OTP form must follow the magic link")
        time.sleep(1.2)
        status, headers, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": "000000"}).encode())
        self.assertNotIn("code=", headers.get("Location", ""))
        self.assertTrue('name="otp"' in html, "wrong code must keep the OTP form")
        time.sleep(1.2)
        status, headers, _ = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
        self.assertEqual(status, 302)
        self.assertIn("code=", headers.get("Location", ""))

    def test_link_lifetime_matches_configuration(self):
        executions = admin(f"/authentication/flows/{AKIS}/executions", self.admin_token).json()
        step = [e for e in executions if e.get("providerId") == MAGIC_LINK][0]
        config = admin(f"/authentication/config/{step['authenticationConfig']}", self.admin_token).json()
        self.assertLessEqual(int(config["config"]["magickey.validity.duration"]), MAX_LIFETIME)

    def test_rest_resource_answers_404(self):
        # Condition 4: the extension's REST resource is disabled by SPI configuration.
        sample = "00000000-0000-4000-8000-000000000000"
        response = istek("GET", f"{self.kc}/realms/platform/{MAGIC_LINK_REST_PATH}?id={sample}&magicKey={sample}")
        self.assertEqual(response.durum, 404)

    def test_continuation_authenticator_is_not_available(self):
        providers = istek("GET", f"{self.kc}/admin/serverinfo", belirtec=self.admin_token).json()["providers"]
        self.assertIn(MAGIC_LINK, providers["authenticator"]["providers"])
        self.assertNotIn(MAGIC_LINK_CONTINUATION, providers["authenticator"]["providers"])

    def test_other_user_cannot_use_a_link_meant_for_someone_else(self):
        # The link is bound to the login request; the browser that started it is the only consumer.
        opener, link = self._request_link(OTHER_USER)
        other = _cerezli_acici()
        _ac(other, tenant_authorize_url())
        status, headers, _ = _keycloak_icinde_izle(other, link, self.kc)
        self.assertNotIn("code=", headers.get("Location", ""))
