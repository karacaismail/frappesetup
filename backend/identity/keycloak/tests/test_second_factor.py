"""Second factor must not be bypassed (Codex review finding E1).

Expected behaviour comes from the contract (section 2, "TOTP ve passkey") and G-78: a user who has
set up TOTP must present a valid code on every browser login, whichever first step was used.
The sample user with a TOTP credential lives in realm/dev-users/platform-users-0.json.
"""

from __future__ import annotations

import hmac
import re
import struct
import time
import unittest
import urllib.parse
from hashlib import sha1

from test_eklentiler import AKIS, SIHIRLI, Mailpit, _ac, _cerezli_acici, _form_hedefi, _keycloak_icinde_izle
from yardimci import admin, canli_var_mi, ortam, yonetici_belirteci

TOTP_USER = "totp.ornek@example.test"
TOTP_PASSWORD = "Ornek-Parola-Totp-2026"
# Keycloak uses the raw UTF-8 bytes of the stored secret (TimeBasedOTP.generateTOTP(String)).
TOTP_SECRET = b"dev-totp-secret-0123456789"


def totp_code(secret: bytes, at: float | None = None, period: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP with HMAC-SHA1, matching Keycloak's default OTP policy."""
    counter = int((at if at is not None else time.time()) // period)
    digest = hmac.new(secret, struct.pack(">Q", counter), sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


class TotpCodeTest(unittest.TestCase):
    def test_rfc6238_reference_vector(self):
        # RFC 6238 appendix B, SHA-1, time 59 -> 94287082 (8 digits).
        self.assertEqual(totp_code(b"12345678901234567890", at=59, digits=8), "94287082")


def _authorize_url() -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": "site-kiraci1",
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": f"{ortam('ATONOTA_SITE_KIRACI1_URL')}/api/method/frappe.integrations.oauth2_logins.login_via_keycloak",
            "state": "test-state",
            "nonce": "test-nonce",
        }
    )
    return f"{ortam('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{query}"


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL missing, live Keycloak test skipped")
class SecondFactorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.admin_token = yonetici_belirteci()
        cls.mailpit = Mailpit(f"http://127.0.0.1:{ortam('MAILPIT_UI_PORT')}")
        executions = admin(f"/authentication/flows/{AKIS}/executions", cls.admin_token).json()
        cls.magic_link_requirement = [e for e in executions if e.get("providerId") == SIHIRLI][0]["requirement"]

    def test_sample_user_has_totp_credential(self):
        user = admin(f"/users?email={TOTP_USER}&exact=true", self.admin_token).json()[0]
        credentials = admin(f"/users/{user['id']}/credentials", self.admin_token).json()
        self.assertIn("otp", {c["type"] for c in credentials})

    def test_password_login_requires_valid_totp(self):
        opener = _cerezli_acici()
        status, _, html = _ac(opener, _authorize_url())
        self.assertEqual(status, 200)
        form = urllib.parse.urlencode({"username": TOTP_USER, "password": TOTP_PASSWORD, "credentialId": ""}).encode()
        status, headers, html = _ac(opener, _form_hedefi(html), form)
        self.assertEqual(status, 200, "password alone must not finish the login")
        self.assertNotIn("code=", headers.get("Location", ""))
        self.assertTrue('name="otp"' in html, "the OTP form must be shown after the password")
        # A wrong code is rejected.
        status, headers, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": "000000"}).encode())
        self.assertNotIn("code=", headers.get("Location", ""))
        self.assertTrue('name="otp"' in html, "wrong code must keep the OTP form")
        # The correct code completes the login with an authorization code.
        status, headers, _ = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": totp_code(TOTP_SECRET)}).encode())
        self.assertEqual(status, 302)
        self.assertIn("code=", headers.get("Location", ""))

    def test_magic_link_cannot_skip_totp(self):
        """A TOTP user must not receive an authorization code from a magic link without a code."""
        if self.magic_link_requirement == "DISABLED":
            # The step is off. The login page must not offer another way, so the bypass is impossible.
            _, _, html = _ac(_cerezli_acici(), _authorize_url())
            self.assertFalse("tryAnotherWay" in html, "login page must not offer the magic link")
            return
        self.mailpit.temizle()
        opener = _cerezli_acici()
        status, _, html = _ac(opener, _authorize_url())
        target = _form_hedefi(html)
        status, _, html = _ac(opener, target, urllib.parse.urlencode({"tryAnotherWay": "on"}).encode())
        executions = admin(f"/authentication/flows/{AKIS}/executions", self.admin_token).json()
        execution_id = [e["id"] for e in executions if e.get("providerId") == SIHIRLI][0]
        status, _, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"authenticationExecution": execution_id}).encode())
        self.assertTrue('name="email"' in html)
        status, _, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"email": TOTP_USER}).encode())
        link = self.mailpit.son_baglanti(TOTP_USER)
        status, headers, html = _keycloak_icinde_izle(opener, link, self.kc)
        location = headers.get("Location", "")
        self.assertNotIn("code=", location, "magic link issued an authorization code without the second factor")
        self.assertTrue('name="otp"' in html, "an OTP form must follow the magic link for a TOTP user")
