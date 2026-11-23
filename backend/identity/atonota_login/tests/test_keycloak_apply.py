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
            if "clientSecret" in shown.get("config", {}):
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
        self.assertIn({"alias": "corporate", "action": "not-in-registry", "enabled": True}, report)
        self.assertFalse([w for w in self.keycloak.writes if "corporate" in w[1]])
        self.assertTrue(self.keycloak.providers["corporate"]["enabled"])

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
                          ("https://evil.test", "api.login.atonota.net"), ("https://u@api.login.atonota.net", "api.login.atonota.net")):
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
