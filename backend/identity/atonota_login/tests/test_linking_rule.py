"""Account linking rule tests (G-160).

Expected rule, from G-160 and the task: an external account is linked by platform and the
platform's stable user number. An e-mail match alone never links. Linking to an existing
account asks the user to sign in again with that account. E-mail access alone is not enough
(G-163). An organization that requires corporate sign-in refuses social sign-in.
"""

import json
import unittest
from pathlib import Path

from atonota_login import platforms

BACKEND = Path(__file__).resolve().parents[3]
REALM_FILE = BACKEND / "identity" / "keycloak" / "realm" / "platform-realm.json"
ENTERPRISE_ROLE = "enterprise-sso-required"
# Keycloak authenticators that link or trust an account by its e-mail address alone.
EMAIL_LINKERS = {"idp-auto-link", "idp-email-verification", "idp-detect-existing-broker-user"}


def flow_tree(realm: dict, alias: str) -> list:
    flows = {f["alias"]: f for f in realm["authenticationFlows"]}
    found = []
    for execution in flows[alias]["authenticationExecutions"]:
        found.append(execution)
        if execution.get("authenticatorFlow"):
            found.extend(flow_tree(realm, execution["flowAlias"]))
    return found


class LinkingRuleTest(unittest.TestCase):
    def setUp(self):
        self.realm = json.loads(REALM_FILE.read_text(encoding="utf-8"))
        self.flows = {f["alias"]: f for f in self.realm["authenticationFlows"]}
        self.configs = {c["alias"]: c["config"] for c in self.realm["authenticatorConfig"]}

    def test_realm_default_first_login_flow_is_ours(self):
        # A provider added later through the admin console also gets the safe flow.
        self.assertEqual(self.realm["firstBrokerLoginFlow"], platforms.FIRST_BROKER_FLOW)
        self.assertTrue(self.flows[platforms.FIRST_BROKER_FLOW]["topLevel"])

    def test_no_step_links_by_e_mail(self):
        for flow in self.realm["authenticationFlows"]:
            for execution in flow["authenticationExecutions"]:
                self.assertNotIn(execution.get("authenticator"), EMAIL_LINKERS, flow["alias"])

    def test_existing_account_needs_confirmation_and_sign_in_again(self):
        tree = flow_tree(self.realm, platforms.FIRST_BROKER_FLOW)
        by_name = {e.get("authenticator"): e for e in tree if e.get("authenticator")}
        self.assertEqual(by_name["idp-confirm-link"]["requirement"], "REQUIRED")
        self.assertEqual(by_name["idp-username-password-form"]["requirement"], "REQUIRED")
        self.assertEqual(by_name["idp-create-user-if-unique"]["requirement"], "ALTERNATIVE")
        # The confirmation and the sign-in are in one branch: confirming alone does not link.
        existing = [e for e in tree if e.get("authenticatorFlow") and e["requirement"] == "ALTERNATIVE"]
        self.assertEqual(len(existing), 1)
        branch = [e.get("authenticator") for e in flow_tree(self.realm, existing[0]["flowAlias"])]
        self.assertLess(branch.index("idp-confirm-link"), branch.index("idp-username-password-form"))

    def test_review_profile_asks_only_for_missing_fields(self):
        tree = flow_tree(self.realm, platforms.FIRST_BROKER_FLOW)
        review = next(e for e in tree if e.get("authenticator") == "idp-review-profile")
        self.assertEqual(self.configs[review["authenticatorConfig"]]["update.profile.on.first.login"], "missing")

    def test_organization_onboarding_stays(self):
        tree = flow_tree(self.realm, platforms.FIRST_BROKER_FLOW)
        self.assertIn("idp-add-organization-member", [e.get("authenticator") for e in tree])

    def test_enterprise_sign_in_rule_refuses_social_sign_in(self):
        tree = flow_tree(self.realm, platforms.POST_BROKER_FLOW)
        names = [e.get("authenticator") for e in tree]
        self.assertIn("conditional-user-role", names)
        self.assertIn("deny-access-authenticator", names)
        self.assertLess(names.index("deny-access-authenticator"), names.index("auth-otp-form"))
        role_step = next(e for e in tree if e.get("authenticator") == "conditional-user-role")
        self.assertEqual(self.configs[role_step["authenticatorConfig"]]["condUserRole"], ENTERPRISE_ROLE)
        self.assertIn(ENTERPRISE_ROLE, {r["name"] for r in self.realm["roles"]["realm"]})

    def test_post_login_flow_succeeds_when_no_condition_applies(self):
        # Live finding (23 November 2026): Keycloak 26.8.2 refuses a post-login flow in which no step
        # ran ("invalid user"). A user without a second factor and without the enterprise role then
        # could not finish any platform sign-in. A final "allow access" step closes the flow.
        steps = self.flows[platforms.POST_BROKER_FLOW]["authenticationExecutions"]
        last = max(steps, key=lambda e: e["priority"])
        self.assertEqual(last.get("authenticator"), "allow-access-authenticator")
        self.assertEqual(last["requirement"], "REQUIRED")
        conditional = [e for e in steps if e is not last]
        self.assertTrue(all(e["requirement"] == "CONDITIONAL" for e in conditional))

    def test_enterprise_role_is_not_a_default_role(self):
        default = self.realm["defaultRole"]["name"]
        role = next(r for r in self.realm["roles"]["realm"] if r["name"] == default)
        self.assertNotIn(ENTERPRISE_ROLE, role["composites"].get("realm", []))

    def test_enterprise_refusal_message_is_translated(self):
        tree = flow_tree(self.realm, platforms.POST_BROKER_FLOW)
        deny = next(e for e in tree if e.get("authenticator") == "deny-access-authenticator")
        key = self.configs[deny["authenticatorConfig"]]["denyErrorMessage"]
        messages = BACKEND / "identity" / "keycloak" / "themes" / "atonota" / "login" / "messages"
        for language in ("tr", "en"):
            text = (messages / f"messages_{language}.properties").read_text(encoding="utf-8")
            self.assertRegex(text, rf"(?m)^{key}=.+", language)


if __name__ == "__main__":
    unittest.main()
