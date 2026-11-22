"""Second factor must not be bypassed (Codex review finding E1).

Expected behaviour comes from the contract (section 2, "TOTP ve passkey") and G-78: a user who has
set up TOTP must present a valid code on every browser login, whichever first step was used.
The sample user with a TOTP credential lives in realm/dev-users/platform-users-0.json.
"""

from __future__ import annotations

import hmac
import struct
import time
import unittest
import urllib.parse
from hashlib import sha1

from test_eklentiler import _ac, _cerezli_acici, _form_hedefi
from yardimci import admin, canli_var_mi, istek, ortam, tenant_authorize_url, tenant_authorize_with_pkce, tenant_callback_url, yonetici_belirteci

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


_used_counters: set = set()


def fresh_totp_code(secret: bytes = TOTP_SECRET, period: int = 30) -> str:
    """A code not used earlier in this run.

    The realm forbids reusing a code (otpPolicyCodeReusable=false). Keycloak accepts the next period's
    code through its look-ahead window of 1, so the second use in a period takes that code. A third
    use waits for the next period.
    """
    while True:
        now = int(time.time())
        for counter in (now // period, now // period + 1):
            if counter not in _used_counters:
                _used_counters.add(counter)
                return totp_code(secret, at=counter * period, period=period)
        time.sleep(period - now % period + 0.5)


class TotpCodeTest(unittest.TestCase):
    def test_rfc6238_reference_vector(self):
        # RFC 6238 appendix B, SHA-1, time 59 -> 94287082 (8 digits).
        self.assertEqual(totp_code(b"12345678901234567890", at=59, digits=8), "94287082")


def _authorize_url() -> str:
    return tenant_authorize_url()


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL missing, live Keycloak test skipped")
class SecondFactorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.admin_token = yonetici_belirteci()

    def setUp(self):
        # The master admin token lives 60 seconds. A long test run outlives the one from setUpClass.
        self.admin_token = yonetici_belirteci()
        # Brute force detection locks a user who logs in twice within quickLoginCheckMilliSeconds.
        # Clear the counter so earlier attempts (or an earlier test) do not lock the sample user.
        user = admin(f"/users?email={TOTP_USER}&exact=true", self.admin_token).json()[0]
        admin(f"/attack-detection/brute-force/users/{user['id']}", self.admin_token, yontem="DELETE")

    def _pause_for_quick_login_check(self):
        # Two attempts within one second count as a quick login and lock the user for 60 seconds.
        time.sleep(1.2)

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
        self._pause_for_quick_login_check()
        # A wrong code is rejected.
        status, headers, html = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": "000000"}).encode())
        self.assertNotIn("code=", headers.get("Location", ""))
        self.assertTrue('name="otp"' in html, "wrong code must keep the OTP form")
        self._pause_for_quick_login_check()
        # The correct code completes the login with an authorization code.
        status, headers, _ = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
        self.assertEqual(status, 302)
        self.assertIn("code=", headers.get("Location", ""))

    def test_authorization_code_is_bound_to_pkce_verifier(self):
        """The code from a full login can only be exchanged with the matching code_verifier."""
        url, verifier = tenant_authorize_with_pkce()
        opener = _cerezli_acici()
        _, _, html = _ac(opener, url)
        form = urllib.parse.urlencode({"username": TOTP_USER, "password": TOTP_PASSWORD, "credentialId": ""}).encode()
        _, _, html = _ac(opener, _form_hedefi(html), form)
        self._pause_for_quick_login_check()
        _, headers, _ = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
        code = urllib.parse.parse_qs(urllib.parse.urlsplit(headers["Location"]).query)["code"][0]
        token_url = f"{self.kc}/realms/platform/protocol/openid-connect/token"
        base = {
            "grant_type": "authorization_code",
            "client_id": "site-kiraci1",
            "client_secret": ortam("ATONOTA_SITE_KIRACI1_SECRET"),
            "redirect_uri": tenant_callback_url(),
            "code": code,
        }
        wrong = istek("POST", token_url, form={**base, "code_verifier": "wrong-" + verifier[:20]})
        self.assertEqual(wrong.durum, 400, "a wrong verifier must be refused")
        self.assertEqual(wrong.json()["error"], "invalid_grant")
        # Keycloak invalidates the code after a failed exchange, so a fresh login is needed for the good case.
        self._pause_for_quick_login_check()
        url, verifier = tenant_authorize_with_pkce()
        opener = _cerezli_acici()
        _, _, html = _ac(opener, url)
        _, _, html = _ac(opener, _form_hedefi(html), form)
        self._pause_for_quick_login_check()
        _, headers, _ = _ac(opener, _form_hedefi(html), urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
        code = urllib.parse.parse_qs(urllib.parse.urlsplit(headers["Location"]).query)["code"][0]
        good = istek("POST", token_url, form={**base, "code": code, "code_verifier": verifier})
        self.assertEqual(good.durum, 200, good.govde[:200])
        self.assertIn("access_token", good.json())
