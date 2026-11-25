"""G-163: email access alone must not add a strong key or recover an account.

A strong key is a passkey or a hardware security key. TOTP is the other second factor.
Conditions under test:
1. A magic link session cannot stand in for an existing strong key. The step after the link
   asks for every strong credential the user already has, including a passkey-only account.
2. The realm binds its own reset flow. The flow never removes or replaces a second factor,
   and a user who has one must present it before a new password is set.
3. First key enrolment and lost key replacement are separate paths. Enrolment is the
   magic link for a user without a strong key. Replacement is the recovery review record in
   press_tr (`PTR Recovery Review`); no Keycloak flow replaces a lost key.
Expected values come from the G-163 gap table (AJA-354, rows 3, 4, 5 and 11).
"""

from __future__ import annotations

import re
import time
import unittest
import urllib.parse

from helpers import admin, admin_token, get_environment_value, live_available, read_realm, request, tenant_authorize_url
from test_extensions import _cookie_opener, _follow_keycloak_redirect, _open
from test_second_factor import TOTP_USER, fresh_totp_code

MAGIC_LINK = "magiclink"
RESET_FLOW = "atonota-reset-credentials"
STRONG_STEPS = {"auth-otp-form", "webauthn-authenticator", "webauthn-authenticator-passwordless"}
# Keycloak steps that delete or replace a second factor or a key.
CREDENTIAL_REMOVAL = {"reset-otp", "webauthn-register", "webauthn-register-passwordless", "CONFIGURE_TOTP"}


class RecoveryFlowFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = read_realm()
        cls.flows = {f["alias"]: f for f in cls.realm["authenticationFlows"]}

    def _tree(self, alias: str) -> list[dict]:
        steps = []
        for execution in sorted(self.flows[alias]["authenticationExecutions"], key=lambda e: e["priority"]):
            steps.append(execution)
            if execution.get("authenticatorFlow"):
                steps.extend(self._tree(execution["flowAlias"]))
        return steps

    def _second_factor_after(self, alias: str, step: str) -> dict:
        executions = sorted(self.flows[alias]["authenticationExecutions"], key=lambda e: e["priority"])
        index = [e.get("authenticator") for e in executions].index(step)
        after = executions[index + 1]
        self.assertTrue(after.get("authenticatorFlow"), alias)
        self.assertEqual(after["requirement"], "CONDITIONAL")
        return self.flows[after["flowAlias"]]

    def test_magic_link_asks_for_every_strong_key_the_user_has(self):
        parent = [f["alias"] for f in self.realm["authenticationFlows"]
                  if MAGIC_LINK in [e.get("authenticator") for e in f["authenticationExecutions"]]]
        self.assertEqual(len(parent), 1)
        second = self._second_factor_after(parent[0], MAGIC_LINK)
        executions = {e.get("authenticator"): e for e in second["authenticationExecutions"]}
        # conditional-user-configured is true when the user has any of the alternatives.
        # Without the passkey step a passkey-only account got a session from the email alone.
        self.assertEqual(executions["conditional-user-configured"]["requirement"], "REQUIRED")
        for step in STRONG_STEPS:
            with self.subTest(step=step):
                self.assertIn(step, executions)
                self.assertEqual(executions[step]["requirement"], "ALTERNATIVE")
                self.assertFalse(executions[step].get("userSetupAllowed"))

    def test_realm_binds_its_own_reset_flow(self):
        self.assertEqual(self.realm.get("resetCredentialsFlow"), RESET_FLOW)
        self.assertTrue(self.flows[RESET_FLOW]["topLevel"])

    def test_reset_flow_never_removes_or_replaces_a_second_factor(self):
        names = {e.get("authenticator") for e in self._tree(RESET_FLOW)}
        self.assertFalse(names & CREDENTIAL_REMOVAL, names & CREDENTIAL_REMOVAL)
        for execution in self._tree(RESET_FLOW):
            with self.subTest(step=execution.get("authenticator") or execution.get("flowAlias")):
                self.assertFalse(execution.get("userSetupAllowed"))

    def test_reset_flow_asks_for_existing_second_factor_before_new_password(self):
        top = [e.get("authenticator") for e in sorted(self.flows[RESET_FLOW]["authenticationExecutions"],
                                                       key=lambda e: e["priority"])]
        self.assertEqual(top[:2], ["reset-credentials-choose-user", "reset-credential-email"])
        self.assertEqual(top[-1], "reset-password")
        second = self._second_factor_after(RESET_FLOW, "reset-credential-email")
        executions = {e.get("authenticator"): e for e in second["authenticationExecutions"]}
        self.assertEqual(executions["conditional-user-configured"]["requirement"], "REQUIRED")
        # The passkey condition must not be here: an email link is never a passkey login.
        self.assertNotIn("conditional-credential", executions)
        for step in STRONG_STEPS:
            with self.subTest(step=step):
                self.assertEqual(executions[step]["requirement"], "ALTERNATIVE")
        required = [e.get("authenticator") for e in self.flows[RESET_FLOW]["authenticationExecutions"]
                    if e["requirement"] == "REQUIRED"]
        self.assertEqual(required, ["reset-credentials-choose-user", "reset-credential-email", "reset-password"])

    def test_first_enrolment_and_lost_key_replacement_are_separate(self):
        # Enrolment: the second factor step after the magic link never offers set-up.
        # Replacement: no flow in the realm removes a key, so a lost key goes to the review record.
        every_step = [e for f in self.realm["authenticationFlows"] for e in f["authenticationExecutions"]]
        self.assertNotIn("reset-otp", {e.get("authenticator") for e in every_step})
        self.assertFalse([e for e in every_step if e.get("userSetupAllowed")])
        self.assertTrue(self.realm["resetPasswordAllowed"])


@unittest.skipUnless(live_available(), "KC_PUBLIC_URL missing, live Keycloak test skipped")
class RecoveryFlowLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = get_environment_value("KC_PUBLIC_URL")
        cls.admin_token = admin_token()
        cls.mailpit = f"http://127.0.0.1:{get_environment_value('MAILPIT_UI_PORT')}"

    def _reset_link(self, email: str):
        request("DELETE", f"{self.mailpit}/api/v1/messages")
        opener = _cookie_opener()
        _, _, html = _open(opener, tenant_authorize_url())
        start = re.search(r'href="([^"]*login-actions/reset-credentials[^"]*)"', html)
        self.assertTrue(start, "login page must offer the forgotten password link")
        _, _, html = _open(opener, urllib.parse.urljoin(self.kc, start.group(1).replace("&amp;", "&")))
        action = re.search(r'<form[^>]*action="([^"]*login-actions/reset-credentials[^"]*)"', html)
        self.assertTrue(action, "reset form expected")
        _open(opener, action.group(1).replace("&amp;", "&"), urllib.parse.urlencode({"username": email}).encode())
        deadline = time.time() + 20
        while time.time() < deadline:
            for message in request("GET", f"{self.mailpit}/api/v1/messages").json().get("messages", []):
                if any(a.get("Address") == email for a in message.get("To", [])):
                    detail = request("GET", f"{self.mailpit}/api/v1/message/{message['ID']}").json()
                    text = (detail.get("Text") or "") + " " + (detail.get("HTML") or "")
                    found = re.search(r"https?://[^\s\"'<>]+login-actions/action-token[^\s\"'<>]+", text)
                    if found:
                        return opener, found.group(0).replace("&amp;", "&")
            time.sleep(1)
        raise AssertionError(f"no reset mail for {email}")

    def _otp_credentials(self, email: str) -> list[str]:
        user = admin(f"/users?email={urllib.parse.quote(email)}&exact=true", self.admin_token).json()[0]
        credentials = admin(f"/users/{user['id']}/credentials", self.admin_token).json()
        return [c["id"] for c in credentials if c["type"] == "otp"]

    def test_server_uses_the_realm_reset_flow(self):
        realm = admin("", self.admin_token).json()
        self.assertEqual(realm["resetCredentialsFlow"], RESET_FLOW)
        names = {e.get("providerId") for e in admin(f"/authentication/flows/{RESET_FLOW}/executions", self.admin_token).json()}
        self.assertFalse(names & CREDENTIAL_REMOVAL)
        self.assertIn("webauthn-authenticator-passwordless", names)

    def test_reset_email_alone_neither_sets_a_password_nor_removes_totp(self):
        before = self._otp_credentials(TOTP_USER)
        self.assertTrue(before, "the sample TOTP user must have a TOTP credential")
        opener, link = self._reset_link(TOTP_USER)
        status, headers, html = _follow_keycloak_redirect(opener, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
        self.assertFalse('name="password-new"' in html, "the email link alone must not open the new password form")
        self.assertTrue('name="otp"' in html, "the existing TOTP must be asked after the email link")
        time.sleep(1.2)
        action = re.search(r'<form[^>]*id="kc-otp-login-form"[^>]*action="([^"]+)"', html).group(1).replace("&amp;", "&")
        selected = re.search(r'name="selectedCredentialId" value="([^"]+)"', html).group(1)
        form = {"selectedCredentialId": selected, "otp": fresh_totp_code()}
        status, headers, html = _open(opener, action, urllib.parse.urlencode(form).encode())
        if status in (302, 303) and headers.get("Location", "").startswith(self.kc):
            status, headers, html = _follow_keycloak_redirect(opener, headers["Location"], self.kc)
        self.assertTrue('name="password-new"' in html, f"HTTP {status}: the new password form follows the TOTP")
        self.assertEqual(self._otp_credentials(TOTP_USER), before)


if __name__ == "__main__":
    unittest.main()
