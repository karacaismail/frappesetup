"""The panel account can call the two AtonotA Login reads (AJA-459).

The panel account is a Frappe Website User. Frappe answers 403 to every method outside
`website_user_allowed_methods`. This test reads `hooks.py` without Frappe, so the local gate
catches a missing entry before a stack trial does.
"""

import ast
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "apps/platform_core/platform_core/hooks.py"
READS = ("platform_core.api.auth.list_login_providers", "platform_core.api.auth.list_linked_accounts")


def website_user_methods():
    tree = ast.parse(HOOKS.read_text(encoding="utf-8"))
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "website_user_allowed_methods"
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError("hooks.py has no website_user_allowed_methods list")


class LoginReadsAccessTests(unittest.TestCase):
    def test_panel_account_may_call_both_reads(self):
        allowed = website_user_methods()
        for method in READS:
            with self.subTest(method=method):
                self.assertIn(method, allowed)

    def test_sign_in_and_service_endpoints_stay_off_the_list(self):
        allowed = website_user_methods()
        for method in (
            "platform_core.api.auth.start_login",
            "platform_core.api.auth.keycloak_callback",
            "platform_core.api.auth.setup_keycloak_login",
            "platform_core.api.identity.provision",
        ):
            with self.subTest(method=method):
                self.assertNotIn(method, allowed)


if __name__ == "__main__":
    unittest.main()
