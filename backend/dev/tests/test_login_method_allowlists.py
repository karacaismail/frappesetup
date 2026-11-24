"""Every AtonotA Login method is on the allow list its caller needs (AJA-480).

Two branches had the same bug on one day. A method was written, but it was not added to an
allow list, so the real backend answered 403 (AJA-459, AJA-410). This test reads the source
without Frappe, so the local gate finds a missing entry before a stack trial does.

The allow lists are these:

- Tenant panel account (a Frappe Website User): `website_user_allowed_methods` in the app hooks.
  `platform_core.shell.native_metadata` refuses every other method to a Website User.
- Press guest: `GUEST_METHODS` in `press_tr/press_identity/request_policy.py` and the
  `@press_customer` paths in `deploy/compose/site.caddy.template`.
- Press signed-in customer: `ACCOUNT_METHOD` in `request_policy.py` and the same Caddy paths.
- Press service (identity-sync): `SERVICE_PARAMETERS` in `press_tr/press_identity/service.py`.
- Press administrator: `ADMIN_METHOD` in `request_policy.py`. It answers only on Tailscale.
- Tenant to identity-sync: the token routes in `identity_sync/server.py` and the preview relay
  targets in `e2e/preview/session_tls.py`.

`EXPECTED` names the caller of each method. A new whitelisted method that is not in `EXPECTED`
fails the test, so its author must decide the caller and the list. A guest flag that does not
match the caller fails too, so no method gets guest access by accident.

Every guest method (`allow_guest=True`) also needs a `rate_limit` decorator (AJA-487). The
whole `platform_core/api` folder is scanned for this, so a new file there is checked too.
`RATE_LIMIT_EXCEPTIONS` names the few methods that are limited in another way.
"""

import ast
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APPS = BACKEND / "apps"
PLATFORM = APPS / "platform_core/platform_core"
PRESS = APPS / "press_tr/press_tr"

# Callers. "guest" has no session: a browser before sign-in, or a provider with a signed body.
# "closed" is a Frappe local sign-in wrapper: guest by Frappe, refused by the Keycloak-only gate.
GUEST, CLOSED, PANEL, ADMIN, SERVICE = "guest", "closed", "panel", "admin", "service"

LOCAL_SIGN_IN_WRAPPERS = (
    "reset_password",
    "update_password",
    "sign_up",
    "send_login_link",
    "login_via_key",
    "login_via_token",
    "login_via_google",
    "login_via_github",
    "login_via_facebook",
    "login_via_frappe",
    "login_via_office365",
    "login_via_salesforce",
    "login_via_fairlogin",
    "login_via_keycloak",
    "custom",
    "ldap_login",
)

EXPECTED = {
    # Tenant sign-in (platform_core.api.auth).
    "platform_core.api.auth.get_login_url": GUEST,
    "platform_core.api.auth.start_login": GUEST,
    "platform_core.api.auth.keycloak_callback": GUEST,
    "platform_core.api.auth.logout": PANEL,
    "platform_core.api.auth.get_csrf_token": PANEL,
    "platform_core.api.auth.setup_keycloak_login": ADMIN,
    "platform_core.api.auth.list_login_providers": PANEL,
    "platform_core.api.auth.list_linked_accounts": PANEL,
    # Keycloak's logout notice. The signed logout token authorizes it.
    "platform_core.api.keycloak_backchannel_logout": GUEST,
    # AtonotA Login decisions and the verification inbox.
    "platform_core.api.atonota_login.evaluate": PANEL,
    "platform_core.api.atonota_login.open_paid_plan": PANEL,
    "platform_core.api.atonota_login.verification_notice": GUEST,
    # identity-sync writes the tenant identity records with its service token.
    "platform_core.api.identity.list_identities": SERVICE,
    "platform_core.api.identity.provision": SERVICE,
    "platform_core.api.identity.set_enabled": SERVICE,
    "platform_core.api.identity.change_email": SERVICE,
    "platform_core.api.identity.anonymize_user": SERVICE,
    # Corporate provider exceptions. System Manager only.
    "platform_core.identity.enterprise_membership.approve_exception": ADMIN,
    "platform_core.identity.enterprise_membership.revoke_exception": ADMIN,
    **{f"platform_core.identity.login_policy.{name}": CLOSED for name in LOCAL_SIGN_IN_WRAPPERS},
    # Press sign-in and account.
    "press_tr.api.auth.get_login_url": GUEST,
    "press_tr.api.auth.keycloak_callback": GUEST,
    "press_tr.api.keycloak_backchannel_logout": GUEST,
    "press_tr.api.account.request_deletion": PANEL,
    "press_tr.api.account.request_recovery": GUEST,
    "press_tr.api.identity.ensure_team": SERVICE,
    "press_tr.api.identity.remove_team_member": SERVICE,
    "press_tr.api.identity.anonymize_user": SERVICE,
    "press_tr.api.identity.list_identities": SERVICE,
    "press_tr.api.maintenance.cleanup_expired_sessions": ADMIN,
}

# Methods that other open branches add. The test checks them once they are in the tree.
# AJA-459 (paperclip/aja-457-login-okuma) owns these methods.
PENDING = {
    "platform_core.api.auth.list_login_providers": "AJA-459",
    "platform_core.api.auth.list_linked_accounts": "AJA-459",
}

# Where AtonotA Login methods live. A new file in these places is scanned too.
SCANNED = (
    *sorted((PLATFORM / "api").rglob("*.py")),
    *sorted((PLATFORM / "identity").rglob("*.py")),
    *sorted(PRESS.rglob("*.py")),
)

# Modules in `platform_core/api` that hold no sign-in method. Their methods skip the caller
# checks above, but their guest methods still need a rate limit. A new file is not on this
# list, so its methods must be named in EXPECTED.
NOT_LOGIN_MODULES = frozenset(
    f"platform_core.api.{name}"
    for name in ("access", "ai", "collection", "meta", "mobile", "mobile_pwa", "model", "shell")
)

# Guest methods without a `rate_limit` decorator, each with its reason.
RATE_LIMIT_EXCEPTIONS = {
    # The contract does not limit a verified logout notice from Keycloak. A rejected notice is
    # limited inside the method, under the `press_tr.rejected_logout` namespace.
    "press_tr.api.keycloak_backchannel_logout": "verified notice is not limited",
}


def module_name(path: Path) -> str:
    app = path.relative_to(APPS).parts[0]
    parts = list(path.relative_to(APPS / app).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or "tests" in path.parts


def whitelist_call(decorator: ast.expr) -> ast.Call | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute) and target.attr == "whitelist":
        return decorator if isinstance(decorator, ast.Call) else ast.Call(func=target, args=[], keywords=[])
    return None


def is_guest(call: ast.Call) -> bool:
    return any(
        keyword.arg == "allow_guest" and isinstance(keyword.value, ast.Constant) and keyword.value.value
        for keyword in call.keywords
    )


def has_rate_limit(function: ast.FunctionDef) -> bool:
    """True when one decorator is `rate_limit`, called or bare, by name or as an attribute."""
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name == "rate_limit":
            return True
    return False


def scan(source: str, module: str) -> dict[str, tuple[bool, bool]]:
    """Full method name, its `allow_guest` value and its rate limit, per whitelisted function."""
    found = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            call = whitelist_call(decorator)
            if call is not None:
                found[f"{module}.{node.name}"] = (is_guest(call), has_rate_limit(node))
    return found


def scanned_methods() -> dict[str, tuple[bool, bool]]:
    found = {}
    for path in SCANNED:
        if not is_test_file(path):
            found.update(scan(path.read_text(encoding="utf-8"), module_name(path)))
    return found


def whitelisted_methods() -> dict[str, bool]:
    """Full method name and its `allow_guest` value, for every whitelisted sign-in function."""
    return {
        method: guest
        for method, (guest, _limited) in scanned_methods().items()
        if method.rpartition(".")[0] not in NOT_LOGIN_MODULES
    }


def unlimited_guest_methods(methods: dict[str, tuple[bool, bool]]) -> list[str]:
    return sorted(
        method
        for method, (guest, limited) in methods.items()
        if guest and not limited and method not in RATE_LIMIT_EXCEPTIONS
    )


def assigned(path: Path, name: str):
    """The literal value of a top-level `name = ...`. Names of earlier constants are resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {}
    value = None
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if not isinstance(target, ast.Name):
                continue
            node = ast.parse(ast.unparse(statement.value), mode="eval").body
            node = ast.fix_missing_locations(_Resolve(constants).visit(node))
            try:
                literal = ast.literal_eval(node)
            except ValueError:
                continue
            constants[target.id] = literal
            if target.id == name:
                value = literal
    if value is None:
        raise AssertionError(f"{path.relative_to(BACKEND)} has no literal {name}")
    return value


class _Resolve(ast.NodeTransformer):
    def __init__(self, constants):
        self.constants = constants

    def visit_Name(self, node):
        if node.id in self.constants:
            return ast.Constant(self.constants[node.id])
        return node


def website_user_methods() -> set[str]:
    allowed = set()
    for hooks in sorted(APPS.glob("*/*/hooks.py")):
        try:
            allowed.update(assigned(hooks, "website_user_allowed_methods"))
        except AssertionError:
            continue
    return allowed


def as_set(value) -> set[str]:
    return {value} if isinstance(value, str) else set(value)


def caddy_customer_paths() -> set[str]:
    text = (BACKEND / "deploy/compose/site.caddy.template").read_text(encoding="utf-8")
    block = re.search(r"@press_customer \{\n(.*?)\n\t\}", text, re.S)
    if block is None:
        raise AssertionError("site.caddy.template has no @press_customer matcher")
    paths = set()
    for line in block.group(1).splitlines():
        words = line.split()
        if words and words[0] == "path":
            paths.update(words[1:])
    return paths


REQUEST_POLICY = PRESS / "press_identity/request_policy.py"
SERVICE_FILE = PRESS / "press_identity/service.py"


class LoginMethodAllowListTests(unittest.TestCase):
    def setUp(self):
        self.methods = whitelisted_methods()

    def test_every_whitelisted_login_method_has_a_named_caller(self):
        unknown = sorted(set(self.methods) - set(EXPECTED))
        self.assertEqual(unknown, [], "Name the caller of each new method in EXPECTED and add it to its list.")

    def test_every_expected_method_exists_or_waits_for_its_branch(self):
        missing = sorted(set(EXPECTED) - set(self.methods) - set(PENDING))
        self.assertEqual(missing, [], "EXPECTED names a method that is not in the source.")

    def test_guest_flag_matches_the_caller(self):
        for method, guest in self.methods.items():
            caller = EXPECTED.get(method)
            if caller is None:
                continue
            with self.subTest(method=method):
                self.assertEqual(guest, caller in (GUEST, CLOSED), f"{method} is {caller}")

    def test_tenant_panel_methods_are_on_the_website_user_list(self):
        allowed = website_user_methods()
        for method in self.methods:
            if not method.startswith("platform_core."):
                continue
            with self.subTest(method=method):
                if EXPECTED.get(method) == PANEL:
                    self.assertIn(method, allowed)
                else:
                    self.assertNotIn(method, allowed)

    def test_press_guest_methods_are_open_to_guests(self):
        guests = set(assigned(REQUEST_POLICY, "GUEST_METHODS"))
        edge = caddy_customer_paths()
        for method in self.methods:
            if not method.startswith("press_tr."):
                continue
            with self.subTest(method=method):
                if EXPECTED.get(method) == GUEST:
                    self.assertIn(method, guests)
                    self.assertIn(f"/api/method/{method}", edge)
                else:
                    self.assertNotIn(method, guests)

    def test_press_customer_methods_pass_the_edge_and_the_route_list(self):
        account = as_set(assigned(REQUEST_POLICY, "ACCOUNT_METHOD"))
        edge = caddy_customer_paths()
        for method in self.methods:
            if EXPECTED.get(method) == PANEL and method.startswith("press_tr."):
                with self.subTest(method=method):
                    self.assertIn(method, account)
                    self.assertIn(f"/api/method/{method}", edge)

    def test_press_service_and_admin_methods_stay_behind_their_lists(self):
        service = set(assigned(SERVICE_FILE, "SERVICE_PARAMETERS"))
        admin = as_set(assigned(REQUEST_POLICY, "ADMIN_METHOD"))
        edge = caddy_customer_paths()
        for method in self.methods:
            if not method.startswith("press_tr."):
                continue
            caller = EXPECTED.get(method)
            with self.subTest(method=method):
                if caller == SERVICE:
                    self.assertIn(method, service)
                if caller == ADMIN:
                    self.assertIn(method, admin)
                if caller in (SERVICE, ADMIN):
                    self.assertNotIn(f"/api/method/{method}", edge)

    def test_tenant_identity_sync_calls_have_a_route_and_a_relay_target(self):
        server = (BACKEND / "identity/identity_sync/identity_sync/server.py").read_text(encoding="utf-8")
        relay = assigned(BACKEND / "e2e/preview/session_tls.py", "RELAY_TARGETS")["sessions"]
        relayed = {path for _method, path in relay}
        called = set()
        for path in PLATFORM.rglob("*.py"):
            if is_test_file(path):
                continue
            text = path.read_text(encoding="utf-8")
            if "identity_sync" in text or "identity-sync" in text:
                called.update(re.findall(r'"(/v1/[a-z][a-z/-]*)"', text))
        self.assertTrue(called, "no tenant call to identity-sync was found")
        for path in sorted(called):
            with self.subTest(path=path):
                self.assertIn(f'"{path}"', server)
                self.assertIn(path, relayed)


class GuestRateLimitTests(unittest.TestCase):
    def test_every_guest_method_has_a_rate_limit(self):
        self.assertEqual(
            unlimited_guest_methods(scanned_methods()),
            [],
            "Add @rate_limit to each guest method, or name it in RATE_LIMIT_EXCEPTIONS with a reason.",
        )

    def test_every_exception_is_a_guest_method_without_a_limit(self):
        methods = scanned_methods()
        for method in RATE_LIMIT_EXCEPTIONS:
            with self.subTest(method=method):
                self.assertEqual(methods.get(method), (True, False), "Remove the stale exception.")


class ScannerSelfTests(unittest.TestCase):
    """The scanner must find methods, or every check above would pass on an empty set."""

    def test_scanner_reads_names_and_guest_flags(self):
        methods = whitelisted_methods()
        self.assertIs(methods["platform_core.api.auth.start_login"], True)
        self.assertIs(methods["platform_core.api.auth.logout"], False)
        self.assertIs(methods["press_tr.api.keycloak_backchannel_logout"], True)
        self.assertIs(methods["press_tr.api.identity.list_identities"], False)

    def test_a_guest_method_without_a_rate_limit_is_found(self):
        source = (
            "@frappe.whitelist(allow_guest=True)\n@rate_limit(limit=5, seconds=60)\ndef limited(): pass\n"
            "@frappe.whitelist(allow_guest=True)\n@frappe.rate_limiter.rate_limit\ndef attribute(): pass\n"
            "@frappe.whitelist(allow_guest=True)\n@rate_limit_namespace('x')\ndef namespace_only(): pass\n"
            "@frappe.whitelist(allow_guest=True)\ndef open_door(): pass\n"
            "@frappe.whitelist()\ndef signed_in(): pass\n"
        )
        self.assertEqual(
            unlimited_guest_methods(scan(source, "sample")), ["sample.namespace_only", "sample.open_door"]
        )

    def test_the_whole_api_folder_is_scanned(self):
        api = PLATFORM / "api"
        self.assertEqual({path for path in SCANNED if path.parent == api}, set(api.glob("*.py")))
        self.assertIn("platform_core.api.ai.mcp", scanned_methods())

    def test_lists_are_read(self):
        self.assertIn("platform_core.api.auth.logout", website_user_methods())
        self.assertIn("/api/method/press_tr.api.auth.get_login_url", caddy_customer_paths())
        self.assertIn("press_tr.api.identity.list_identities", assigned(SERVICE_FILE, "SERVICE_PARAMETERS"))


if __name__ == "__main__":
    unittest.main()
