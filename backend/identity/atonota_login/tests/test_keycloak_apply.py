"""Offline tests of the apply step (G-159, review finding 4 and 9).

A fake Admin API stands in for Keycloak. The expected rules come from G-159: a platform with all
secrets opens, a platform without one closes and keeps no secret, other providers are not changed,
and no secret value appears in a message.
"""

import copy
import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from atonota_login import keycloak_apply, platforms
from atonota_login.keycloak_apply import ApplyError

MASK = "**********"


def record(alias):
    upper = alias.upper().replace("-", "_")
    return {
        "alias": alias, "providerId": "oidc", "displayName": alias.title(),
        "authorizationHost": "login.example.test",
        "secrets": {"clientId": f"ATONOTA_{upper}_CLIENT_ID", "clientSecret": f"ATONOTA_{upper}_CLIENT_SECRET"},
        "config": {"syncMode": "IMPORT", "filteredByClaim": "true", "claimFilterName": "email_verified",
                   "claimFilterValue": "true"},
    }


class FakeKeycloak:
    def __init__(self, providers):
        self.providers = {p["alias"]: copy.deepcopy(p) for p in providers}
        self.writes = []

    def __call__(self, method, path, payload=None):
        if payload is not None:
            self.writes.append((method, path, json.dumps(payload)))
        if path == "/identity-provider/instances" and method == "GET":
            return 200, [copy.deepcopy(p) for p in self.providers.values()]
        if path == "/identity-provider/instances" and method == "POST":
            self.providers[payload["alias"]] = copy.deepcopy(payload)
            return 201, None
        alias = path.rsplit("/", 1)[1]
        if method == "GET":
            if alias not in self.providers:
                return 404, None
            shown = copy.deepcopy(self.providers[alias])
            if "clientSecret" in (shown.get("config") or {}):
                shown["config"]["clientSecret"] = MASK
            return 200, shown
        if method == "PUT":
            self.providers[alias] = copy.deepcopy(payload)
            return 204, None
        return 500, None


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for alias in ("open-one", "closed-one"):
            (Path(self.folder.name) / f"{alias}.json").write_text(json.dumps(record(alias)), encoding="utf-8")
        self.registry = platforms.load_platforms(Path(self.folder.name))
        self.secret = secrets.token_urlsafe(24)
        self.environment = {"ATONOTA_OPEN_ONE_CLIENT_ID": "client-1", "ATONOTA_OPEN_ONE_CLIENT_SECRET": self.secret}
        old_secret = secrets.token_urlsafe(24)
        self.kept_secret = old_secret
        corporate = {"alias": "corporate", "providerId": "oidc", "enabled": True, "config": {"clientId": "c"}}
        closed = {"alias": "closed-one", "providerId": "oidc", "enabled": True, "hideOnLogin": False,
                  "internalId": "id-1", "config": {"clientId": "old", "clientSecret": old_secret, "extra": "kept"}}
        self.keycloak = FakeKeycloak([corporate, closed])

    def test_missing_platform_is_created_open(self):
        report = keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        self.assertIn({"alias": "open-one", "action": "created", "enabled": True}, report)
        created = self.keycloak.providers["open-one"]
        self.assertTrue(created["enabled"])
        self.assertFalse(created["hideOnLogin"])
        self.assertEqual(created["config"]["clientSecret"], self.secret)

    def test_closed_platform_keeps_no_secret_and_hides(self):
        keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        closed = self.keycloak.providers["closed-one"]
        self.assertFalse(closed["enabled"])
        self.assertTrue(closed["hideOnLogin"])
        self.assertEqual(closed["config"]["clientSecret"], "")
        self.assertEqual(closed["config"]["clientId"], "")
        self.assertEqual(closed["config"]["extra"], "kept")
        self.assertEqual(closed["internalId"], "id-1")

    def test_masked_secret_is_never_written_back(self):
        keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        for _, _, body in self.keycloak.writes:
            self.assertNotIn(MASK, body)
            self.assertNotIn(self.kept_secret, body)

    def test_other_providers_are_listed_not_changed(self):
        report = keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        self.assertIn({"alias": "corporate", "action": "not-in-registry-unverified-email", "enabled": True}, report)
        self.assertFalse([w for w in self.keycloak.writes if "corporate" in w[1]])
        self.assertTrue(self.keycloak.providers["corporate"]["enabled"])

    def test_provider_outside_the_registry_is_flagged_by_its_e_mail_rule(self):
        # Review 1, important 3: a corporate provider without the email_verified rule can pre-hijack an
        # account. The command does not change it, but names it so the operator sees it.
        safe = {"alias": "corporate-safe", "providerId": "oidc", "enabled": True,
                "config": dict(platforms.VERIFIED_EMAIL_CLAIM)}
        self.keycloak.providers["corporate-safe"] = safe
        report = keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        actions = {line["alias"]: line["action"] for line in report}
        self.assertEqual(actions["corporate"], "not-in-registry-unverified-email")
        self.assertEqual(actions["corporate-safe"], "not-in-registry")

    def test_provider_with_null_config_does_not_stop_the_command(self):
        # Review 2, finding 1: Keycloak may return "config": null. The command must not crash.
        self.keycloak.providers["closed-one"]["config"] = None
        self.keycloak.providers["corporate"]["config"] = None
        report = keycloak_apply.apply_registry(self.keycloak, self.registry, self.environment)
        actions = {line["alias"]: line["action"] for line in report}
        self.assertEqual(actions["closed-one"], "updated")
        self.assertEqual(actions["corporate"], "not-in-registry-unverified-email")
        closed = self.keycloak.providers["closed-one"]
        self.assertFalse(closed["enabled"])
        self.assertEqual(closed["config"]["clientSecret"], "")

    def test_errors_hold_no_secret(self):
        def failing(method, path, payload=None):
            return (404, None) if method == "GET" else (500, None)
        with self.assertRaises(ApplyError) as raised:
            keycloak_apply.apply_registry(failing, self.registry, self.environment)
        self.assertNotIn(self.secret, str(raised.exception))


class KeycloakAddressTest(unittest.TestCase):
    def test_remote_needs_https_and_the_named_host(self):
        self.assertEqual(
            keycloak_apply.checked_keycloak_url("https://api.login.atonota.net", "api.login.atonota.net"),
            "https://api.login.atonota.net")
        for url, host in (("https://api.login.atonota.net", None), ("http://api.login.atonota.net", "api.login.atonota.net"),
                          ("https://evil.test", "api.login.atonota.net"), ("https://u@login.example.test", "login.example.test")):
            with self.subTest(url=url), self.assertRaises(ApplyError):
                keycloak_apply.checked_keycloak_url(url, host)

    def test_local_name_must_resolve_to_loopback(self):
        # Review finding 9: an http *.localhost name gets the admin password only if it is loopback.
        loopback = [(2, 1, 6, "", ("127.0.0.1", 0))]
        elsewhere = [(2, 1, 6, "", ("192.0.2.10", 0))]
        with mock.patch("socket.getaddrinfo", return_value=loopback):
            self.assertEqual(keycloak_apply.checked_keycloak_url("http://identity.localhost:5280"),
                             "http://identity.localhost:5280")
        with mock.patch("socket.getaddrinfo", return_value=elsewhere), self.assertRaises(ApplyError):
            keycloak_apply.checked_keycloak_url("http://identity.localhost:5280")


if __name__ == "__main__":
    unittest.main()


class CommandTest(unittest.TestCase):
    """Command line checks (review 1, minor 8 and 9)."""

    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        path = Path(__file__).resolve().parents[1] / "bin" / "atonota-login"
        loader = importlib.machinery.SourceFileLoader("atonota_login_command", str(path))
        spec = importlib.util.spec_from_loader("atonota_login_command", loader)
        cls.command = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.command)

    def run_command(self, *arguments):
        import contextlib
        import io
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                code = self.command.main(list(arguments))
            except SystemExit as stop:
                code = stop.code
        return code, output.getvalue()

    def test_env_accepts_only_known_environments(self):
        for name in ("../x", "dev", "/etc/passwd", "alpha/../prod"):
            with self.subTest(name=name):
                self.assertNotEqual(self.run_command("redirects", "--env", name)[0], 0)
        for name in ("alpha", "beta", "rc", "prod", "all"):
            with self.subTest(name=name):
                self.assertEqual(self.run_command("redirects", "--env", name)[0], 0)

    def write_local_http_registry(self, folder):
        local = record("local-oidc")
        local["config"]["tokenUrl"] = "http://localhost/token"
        (Path(folder) / "local-oidc.json").write_text(json.dumps(local), encoding="utf-8")

    def test_registry_with_local_http_is_refused_without_the_development_switch(self):
        # Review 2, finding 2: the realm file and the platform list reach every environment.
        with tempfile.TemporaryDirectory() as folder:
            self.write_local_http_registry(folder)
            self.assertNotEqual(self.run_command("--platforms-dir", folder, "render", "--check")[0], 0)
            self.assertNotEqual(self.run_command("--platforms-dir", folder, "redirects", "--env", "prod")[0], 0)

    def test_development_switch_only_for_apply_to_a_local_keycloak(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write_local_http_registry(folder)
            for arguments in (("render", "--check"), ("redirects", "--env", "prod")):
                with self.subTest(arguments=arguments):
                    code, _ = self.run_command("--platforms-dir", folder, "--allow-local-http", *arguments)
                    self.assertNotEqual(code, 0)
            remote = {"KC_PUBLIC_URL": "https://api.login.atonota.net", "KC_BOOTSTRAP_ADMIN_USERNAME": "admin",
                      "KC_BOOTSTRAP_ADMIN_PASSWORD": "not-used"}
            with mock.patch.dict("os.environ", remote), \
                    mock.patch.object(keycloak_apply, "admin_caller") as caller:
                code, _ = self.run_command("--platforms-dir", folder, "--allow-local-http", "apply", "--from-env",
                                           "--remote-host", "api.login.atonota.net")
            self.assertNotEqual(code, 0)
            caller.assert_not_called()

    def test_development_switch_lets_apply_reach_a_local_keycloak(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write_local_http_registry(folder)
            local = {"KC_PUBLIC_URL": "http://identity.localhost:5280", "KC_BOOTSTRAP_ADMIN_USERNAME": "admin",
                     "KC_BOOTSTRAP_ADMIN_PASSWORD": "not-used"}
            loopback = [(2, 1, 6, "", ("127.0.0.1", 0))]
            with mock.patch.dict("os.environ", local), mock.patch("socket.getaddrinfo", return_value=loopback), \
                    mock.patch.object(keycloak_apply, "admin_caller", return_value=FakeKeycloak([])):
                code, output = self.run_command("--platforms-dir", folder, "--allow-local-http", "apply", "--from-env")
            self.assertEqual(code, 0)
            self.assertIn("local-oidc: created, closed", output)

    def test_public_url_accepts_only_a_local_address(self):
        self.assertNotEqual(self.run_command("redirects", "--public-url", "https://evil.example")[0], 0)
        code, output = self.run_command("redirects", "--public-url", "http://identity.localhost:5280")
        self.assertEqual(code, 0)
        self.assertIn("http://identity.localhost:5280/realms/platform/broker/", output)
