"""Who may call the two atonota_login reads (AJA-459, AJA-516).

The panel account is a Frappe Website User. Frappe answers 403 to every method outside
`website_user_allowed_methods`. A guest gets 403 and "is not whitelisted" for every method
without `allow_guest=True`. This test reads the source without Frappe, so the local gate
catches a wrong decorator or a missing list entry before a stack trial does.

The board decided on 24 November 2026 (AJA-516):

- `list_login_providers` is open to guests. The sign-in screen calls it before sign-in. The
  panel contract says so: `atonota-web`, `src/auth/README.md`, G-159 ("Uç oturum istemez").
- `list_linked_accounts` still needs a session.
- The open method takes GET only, has a rate limit and returns only `alias` and `display_name`.
"""

import ast
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
HOOKS = BACKEND / "apps/platform_core/platform_core/hooks.py"
AUTH = BACKEND / "apps/platform_core/platform_core/api/auth.py"
LOGIN_ACCOUNTS = BACKEND / "apps/platform_core/platform_core/identity/login_accounts.py"
SERVICE_READS = BACKEND / "identity/identity_sync/identity_sync/login_reads.py"
CONTRACT = BACKEND / "contracts/platform_core-identity.openapi.yaml"
PROVIDERS = "platform_core.api.auth.list_login_providers"
LINKED = "platform_core.api.auth.list_linked_accounts"
READS = (PROVIDERS, LINKED)

# Field names of one row, per side. The panel side is copied from `atonota-web`
# `src/api/login-client.ts` (interface `LoginProvider`) and `src/auth/README.md` line 99.
PANEL_PROVIDER_FIELDS = {"alias", "display_name"}
PANEL_LINKED_FIELDS = {"alias", "display_name", "linked"}


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


def function(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path.name} has no function {name}")


def decorator_keywords(node: ast.FunctionDef, name: str) -> dict[str, object]:
    """The keywords of the decorator `name`, as source text. Fails when the decorator is missing."""
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        found = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if found == name:
            return {keyword.arg: ast.unparse(keyword.value) for keyword in decorator.keywords}
    raise AssertionError(f"{node.name} has no @{name}(...) decorator")


def called_names(node: ast.FunctionDef) -> set[str]:
    names = set()
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            target = call.func
            names.add(target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", ""))
    return names


def dict_keys(node: ast.AST) -> set[str]:
    return {key.value for key in node.keys if isinstance(key, ast.Constant)} if isinstance(node, ast.Dict) else set()


def contract_block(path: str) -> str:
    """The text of one path in the OpenAPI file, up to the next path."""
    text = CONTRACT.read_text(encoding="utf-8")
    match = re.search(rf"^  /{re.escape(path)}:\n(.*?)(?=^  /|^components:)", text, re.S | re.M)
    if match is None:
        raise AssertionError(f"the contract has no path /{path}")
    return match.group(1)


def contract_schema_fields(name: str) -> set[str]:
    """The property names of the rows of `providers` in one component schema."""
    text = CONTRACT.read_text(encoding="utf-8")
    match = re.search(rf"^    {name}:\n(.*?)(?=^    [A-Za-z]+:\n)", text, re.S | re.M)
    if match is None:
        raise AssertionError(f"the contract has no schema {name}")
    rows = re.search(r"items:\n(.*?)additionalProperties: false", match.group(1), re.S)
    properties = re.search(r"properties:\n(.*)", rows.group(1), re.S).group(1)
    return set(re.findall(r"^ {14}([a-z_]+):", properties, re.M))


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


class GuestProviderListTests(unittest.TestCase):
    """AJA-516: the sign-in screen reads the platform list without a session."""

    def setUp(self):
        self.providers = function(AUTH, "list_login_providers")
        self.linked = function(AUTH, "list_linked_accounts")

    def test_provider_list_is_open_to_guests_with_get_only(self):
        keywords = decorator_keywords(self.providers, "whitelist")
        self.assertEqual(keywords.get("allow_guest"), "True")
        self.assertEqual(keywords.get("methods"), "['GET']")

    def test_provider_list_does_not_ask_for_a_session(self):
        self.assertNotIn("require_session", called_names(self.providers))

    def test_provider_list_is_never_stored(self):
        # The session check set `no-store` before. The open method must still set it.
        self.assertIn("no_store", called_names(self.providers))

    def test_provider_list_is_limited_per_address(self):
        # All guests are the user "Guest". A per-user limit would be one bucket for every visitor,
        # so one visitor could use up the limit of all. Frappe counts a guest limit per IP address.
        keywords = decorator_keywords(self.providers, "rate_limit")
        self.assertEqual(keywords.get("limit"), "login_accounts.RATE_LIMIT")
        self.assertEqual(keywords.get("seconds"), "60")
        self.assertNotIn(keywords.get("user_based"), ("True",))

    def test_linked_accounts_still_needs_a_session(self):
        keywords = decorator_keywords(self.linked, "whitelist")
        self.assertNotIn("allow_guest", keywords)
        self.assertEqual(keywords.get("methods"), "['GET']")
        self.assertIn("require_session", called_names(self.linked))
        self.assertEqual(decorator_keywords(self.linked, "rate_limit").get("user_based"), "True")

    def test_contract_shows_the_provider_list_open_and_the_linked_list_closed(self):
        providers = contract_block(PROVIDERS)
        linked = contract_block(LINKED)
        self.assertRegex(providers, r"\n      security: \[\]\n")
        self.assertNotIn("frappeSession", providers)
        self.assertIn("frappeSession", linked)


class ProviderFieldTests(unittest.TestCase):
    """The panel, the tenant contract, the tenant code and identity-sync name the same fields."""

    def test_tenant_rows_carry_only_the_panel_fields(self):
        rows = function(LOGIN_ACCOUNTS, "_provider_rows")
        built = set()
        for node in ast.walk(rows):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "item" for t in node.targets):
                built |= dict_keys(node.value)
            if isinstance(node, ast.Subscript) and getattr(node.value, "id", None) == "item":
                if isinstance(node.slice, ast.Constant) and isinstance(node.ctx, ast.Store):
                    built.add(node.slice.value)
        self.assertEqual(built, PANEL_LINKED_FIELDS)
        self.assertEqual(built - {"linked"}, PANEL_PROVIDER_FIELDS)

    def test_tenant_reply_has_only_the_providers_key(self):
        reply = function(LOGIN_ACCOUNTS, "list_login_providers").body[-1]
        self.assertIsInstance(reply, ast.Return)
        self.assertEqual(dict_keys(reply.value), {"providers"})

    def test_identity_sync_rows_carry_only_the_panel_fields(self):
        rows = function(SERVICE_READS, "provider_list").body[-1].value
        comprehension = rows.values[0]
        self.assertEqual(dict_keys(comprehension.elt), PANEL_PROVIDER_FIELDS)

    def test_contract_rows_carry_only_the_panel_fields(self):
        self.assertEqual(contract_schema_fields("LoginProviderList"), PANEL_PROVIDER_FIELDS)
        self.assertEqual(contract_schema_fields("LinkedAccounts"), PANEL_LINKED_FIELDS)


if __name__ == "__main__":
    unittest.main()
