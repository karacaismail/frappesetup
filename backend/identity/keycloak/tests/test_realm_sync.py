"""T-11: the development realm sync applies the realm file's clients and scopes to a kept database.

Expected values come from the realm file (realm/platform-realm.json) and the MVP test 2 report:
a kept Keycloak database must give mobile-app the optional scopes "mobile" and "aud-site-tenant1".
Users and sessions stay. A fake Admin API stands in for Keycloak.
"""

from __future__ import annotations

import copy
import io
import itertools
import json
import runpy
import subprocess
import sys
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout

from helpers import DIRECTORY, jwt_payload, live_available, read_realm

SCRIPT = DIRECTORY / "bin" / "sync-dev-realm.py"
SECRET_VALUE = "synthetic-secret-value-123"


def module():
    return runpy.run_path(str(SCRIPT))


def placeholder_values(realm: dict) -> dict:
    text = json.dumps({"clients": realm["clients"], "clientScopes": realm["clientScopes"]})
    names = set(module()["PLACEHOLDER"].findall(text))
    return {name: SECRET_VALUE if "SECRET" in name else f"value-{name.lower()}" for name, _ in names}


class FakeAdmin:
    """Keeps the small part of the Keycloak Admin API state the sync touches."""

    def __init__(self):
        self.ids = (f"id-{number}" for number in itertools.count(1))
        self.clients: dict[str, dict] = {}
        self.scopes: dict[str, dict] = {}
        self.bindings: dict[tuple[str, str], set[str]] = {}
        self.realm_defaults = {"default": set(), "optional": set()}
        self.scope_roles: dict[tuple[str, str], set[str]] = {}
        self.calls: list[tuple[str, str]] = []

    # State helpers for the test setup.
    def add_scope(self, rep: dict) -> str:
        scope_id = next(self.ids)
        mappers = [dict(mapper, id=next(self.ids)) for mapper in rep.get("protocolMappers", [])]
        self.scopes[scope_id] = dict(copy.deepcopy(rep), id=scope_id, protocolMappers=mappers)
        return scope_id

    def scope_id(self, name: str) -> str | None:
        return next((key for key, value in self.scopes.items() if value["name"] == name), None)

    def add_client(self, rep: dict) -> str:
        client_id = next(self.ids)
        rep = copy.deepcopy(rep)
        for kind in ("default", "optional"):
            names = rep.pop(f"{kind}ClientScopes", [])
            self.bindings[(client_id, kind)] = {self.scope_id(name) for name in names if self.scope_id(name)}
        mappers = [dict(mapper, id=next(self.ids)) for mapper in rep.pop("protocolMappers", [])]
        self.clients[client_id] = dict(rep, id=client_id, protocolMappers=mappers)
        return client_id

    def client_named(self, client_id: str) -> dict:
        return next(value for value in self.clients.values() if value["clientId"] == client_id)

    def bound(self, client_id: str, kind: str) -> set[str]:
        internal = self.client_named(client_id)["id"]
        return {self.scopes[scope]["name"] for scope in self.bindings[(internal, kind)]}

    def writes(self) -> list[tuple[str, str]]:
        return [call for call in self.calls if call[0] != "GET"]

    # The Admin API.
    def __call__(self, method: str, path: str, payload=None):
        self.calls.append((method, path))
        parts = urllib.parse.urlsplit(path)
        segments = parts.path.strip("/").split("/")
        query = urllib.parse.parse_qs(parts.query)
        if segments == ["clients"] and method == "GET":
            return [self.public_client(c) for c in self.clients.values() if c["clientId"] == query["clientId"][0]]
        if segments == ["clients"] and method == "POST":
            self.add_client(payload)
            return None
        if segments[0] == "clients" and len(segments) == 2:
            if method == "GET":
                return self.public_client(self.clients[segments[1]])
            if method == "PUT":
                self.assert_no_scope_lists(payload)
                mappers = self.clients[segments[1]]["protocolMappers"]
                self.clients[segments[1]] = dict(copy.deepcopy(payload), protocolMappers=mappers)
                return None
        if segments[0] == "clients" and segments[2] in ("default-client-scopes", "optional-client-scopes"):
            kind = segments[2].split("-")[0]
            bound = self.bindings[(segments[1], kind)]
            if len(segments) == 3 and method == "GET":
                return [{"id": scope, "name": self.scopes[scope]["name"]} for scope in sorted(bound)]
            if method == "PUT":
                bound.add(segments[3])
                return None
            if method == "DELETE":
                bound.discard(segments[3])
                return None
        if segments[0] == "clients" and segments[2] == "roles" and method == "GET":
            return {"id": f"role-{segments[3]}", "name": segments[3], "clientRole": True, "containerId": segments[1]}
        if segments == ["client-scopes"] and method == "GET":
            return [{key: value for key, value in s.items() if key != "protocolMappers"} for s in self.scopes.values()]
        if segments == ["client-scopes"] and method == "POST":
            self.add_scope(payload)
            return None
        if segments[0] == "client-scopes" and len(segments) == 2 and method == "PUT":
            self.assertion(payload.get("id") == segments[1] and "protocolMappers" not in payload)
            mappers = self.scopes[segments[1]]["protocolMappers"]
            self.scopes[segments[1]] = dict(copy.deepcopy(payload), protocolMappers=mappers)
            return None
        if "protocol-mappers" in segments:
            owner = self.clients if segments[0] == "clients" else self.scopes
            mappers = owner[segments[1]]["protocolMappers"]
            if len(segments) == 4 and method == "GET":
                return copy.deepcopy(mappers)
            if len(segments) == 4 and method == "POST":
                mappers.append(dict(copy.deepcopy(payload), id=next(self.ids)))
                return None
            if len(segments) == 5 and method == "PUT":
                index = next(i for i, mapper in enumerate(mappers) if mapper["id"] == segments[4])
                mappers[index] = copy.deepcopy(payload)
                return None
        if segments[0] in ("default-default-client-scopes", "default-optional-client-scopes"):
            kind = segments[0].split("-")[1]
            if len(segments) == 1 and method == "GET":
                return [{"id": s, "name": self.scopes[s]["name"]} for s in sorted(self.realm_defaults[kind])]
            if method == "PUT":
                self.realm_defaults[kind].add(segments[1])
                return None
        if segments[0] == "client-scopes" and segments[2] == "scope-mappings":
            roles = self.scope_roles.setdefault((segments[1], segments[4]), set())
            if method == "GET":
                return [{"id": f"role-{name}", "name": name} for name in sorted(roles)]
            if method == "POST":
                roles.update(role["name"] for role in payload)
                return None
        raise AssertionError(f"Unexpected Admin API call: {method} {path}")

    @staticmethod
    def public_client(rep):
        return {key: value for key, value in copy.deepcopy(rep).items() if key != "protocolMappers"}

    @staticmethod
    def assert_no_scope_lists(payload):
        for key in ("defaultClientScopes", "optionalClientScopes", "protocolMappers"):
            if key in payload:
                raise AssertionError(f"Client PUT must not carry {key}; bindings have their own endpoints.")

    @staticmethod
    def assertion(condition):
        if not condition:
            raise AssertionError("Unexpected request body.")


class RealmSyncTest(unittest.TestCase):
    def setUp(self):
        self.sync = module()
        self.realm = read_realm()
        self.values = placeholder_values(self.realm)
        self.file = self.sync["resolve"](
            {key: self.realm[key] for key in self.sync["SYNCED_KEYS"] if key in self.realm}, self.values
        )

    def fresh_admin(self) -> FakeAdmin:
        """A database that imported the current realm file."""
        admin = FakeAdmin()
        admin.add_client({"clientId": "realm-management", "name": "realm-management"})
        for scope in self.file["clientScopes"]:
            admin.add_scope(scope)
        for client in self.file["clients"]:
            admin.add_client(client)
        for kind, key in (("default", "defaultDefaultClientScopes"), ("optional", "defaultOptionalClientScopes")):
            admin.realm_defaults[kind] = {admin.scope_id(name) for name in self.file[key]}
        for client, mappings in self.file["clientScopeMappings"].items():
            internal = admin.client_named(client)["id"]
            for mapping in mappings:
                admin.scope_roles[(admin.scope_id(mapping["clientScope"]), internal)] = set(mapping["roles"])
        return admin

    def stale_admin(self) -> FakeAdmin:
        """The kept database from the MVP test 2 report: mobile-app lacks its two optional scopes."""
        admin = self.fresh_admin()
        mobile_scope = admin.scope_id("mobile")
        del admin.scopes[mobile_scope]
        for bound in admin.bindings.values():
            bound.discard(mobile_scope)
        audience = admin.scopes[admin.scope_id("aud-site-tenant1")]
        audience["protocolMappers"] = []
        audience["description"] = "old description"
        mobile = admin.client_named("mobile-app")
        admin.bindings[(mobile["id"], "optional")] = set()
        # A wrong category: the old client had acr as optional instead of default.
        acr = admin.scope_id("acr")
        admin.bindings[(mobile["id"], "default")].discard(acr)
        admin.bindings[(mobile["id"], "optional")].add(acr)
        mobile["attributes"]["pkce.code.challenge.method"] = "plain"
        # An operator added another tenant's audience scope (create-tenant-client.py); it must stay.
        extra = admin.add_scope({"name": "aud-site-acme", "protocol": "openid-connect"})
        admin.bindings[(mobile["id"], "optional")].add(extra)
        return admin

    def run_sync(self, admin) -> list[str]:
        return self.sync["sync_realm"](self.file, admin)

    def test_kept_database_gets_the_mobile_scopes_of_the_realm_file(self):
        admin = self.stale_admin()
        self.assertNotIn("mobile", admin.bound("mobile-app", "optional"))

        changes = self.run_sync(admin)

        self.assertTrue(changes)
        self.assertEqual(admin.bound("mobile-app", "optional"), {"aud-site-tenant1", "mobile", "aud-site-acme"})
        self.assertEqual(admin.bound("mobile-app", "default"), set(self.file_client("mobile-app")["defaultClientScopes"]))
        self.assertEqual(admin.client_named("mobile-app")["attributes"]["pkce.code.challenge.method"], "S256")
        audience = admin.scopes[admin.scope_id("aud-site-tenant1")]
        self.assertEqual([mapper["name"] for mapper in audience["protocolMappers"]], ["aud-site-tenant1"])
        self.assertEqual(audience["protocolMappers"][0]["config"]["included.client.audience"], "site-tenant1")
        self.assertEqual(audience["description"], self.file_scope("aud-site-tenant1")["description"])
        self.assertIsNotNone(admin.scope_id("mobile"))

    def test_second_run_writes_nothing(self):
        admin = self.stale_admin()
        self.run_sync(admin)
        admin.calls.clear()

        self.assertEqual(self.run_sync(admin), [])
        self.assertEqual(admin.writes(), [])

    def test_database_that_matches_the_file_gets_no_writes(self):
        admin = self.fresh_admin()
        self.assertEqual(self.run_sync(admin), [])
        self.assertEqual(admin.writes(), [])

    def test_missing_client_is_created_and_users_and_sessions_are_never_touched(self):
        admin = self.stale_admin()
        mobile = admin.client_named("mobile-app")
        del admin.clients[mobile["id"]]

        self.run_sync(admin)

        self.assertEqual(admin.bound("mobile-app", "optional"), {"aud-site-tenant1", "mobile"})
        for method, path in admin.calls:
            with self.subTest(call=(method, path)):
                self.assertNotRegex(path, r"/(users|sessions|logout|attack-detection|partialImport)")
                if method == "DELETE":
                    self.assertRegex(path, r"^/clients/[^/]+/(default|optional)-client-scopes/[^/]+$")

    def test_client_secret_comes_from_the_environment_and_is_never_reported(self):
        admin = self.stale_admin()
        admin.client_named("site-tenant1")["secret"] = "old-secret"

        changes = self.run_sync(admin)

        self.assertEqual(admin.client_named("site-tenant1")["secret"], SECRET_VALUE)
        self.assertNotIn(SECRET_VALUE, "\n".join(changes))
        self.assertNotIn("old-secret", "\n".join(changes))

    def test_unknown_placeholder_without_default_is_refused_by_name(self):
        values = dict(self.values)
        values.pop("ATONOTA_MOBILE_REDIRECT_URI")
        with self.assertRaisesRegex(self.sync["SyncError"], "ATONOTA_MOBILE_REDIRECT_URI"):
            self.sync["resolve"]({"clients": self.realm["clients"]}, values)

    def test_placeholder_rules_follow_keycloak_import(self):
        resolved = self.sync["resolve"](
            {"a": "${ATONOTA_X}", "b": "${ATONOTA_Y:fallback}", "c": "${emailScopeConsentText}", "d": "x-${ATONOTA_X}"},
            {"ATONOTA_X": "one"},
        )
        self.assertEqual(resolved, {"a": "one", "b": "fallback", "c": "${emailScopeConsentText}", "d": "x-one"})

    def test_only_local_development_keycloak_is_accepted(self):
        accepted = ("http://identity.localhost:6570", "http://127.0.0.1:6570", "http://localhost:8080")
        refused = (
            "https://identity.example.com",
            "http://identity.localhost.example.com:6570",
            "http://user@identity.localhost:6570",
            "http://identity.localhost:6570/path",
            "ftp://identity.localhost",
        )
        for url in accepted:
            with self.subTest(url=url):
                self.assertEqual(self.sync["local_keycloak_url"](url), url)
        for url in refused:
            with self.subTest(url=url), self.assertRaises(self.sync["SyncError"]):
                self.sync["local_keycloak_url"](url)

    def test_command_refuses_a_remote_keycloak_before_any_request(self):
        payload = {"keycloak_url": "https://identity.example.com", "realm": self.realm, "values": self.values,
                   "admin_username": "admin", "admin_password": SECRET_VALUE}
        out, err = io.StringIO(), io.StringIO()
        main = self.sync["main"]
        calls = []
        main.__globals__["admin_caller"] = lambda *args: calls.append(args)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--stdin"], stdin=io.StringIO(json.dumps(payload)))
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertNotIn(SECRET_VALUE, out.getvalue() + err.getvalue())

    def test_script_text_runs_with_python_c_as_the_stack_sends_it(self):
        # The stack passes the script text with "python -I -c"; there is no __file__ then.
        payload = {"keycloak_url": "https://identity.example.com", "realm": self.realm, "values": self.values,
                   "admin_username": "admin", "admin_password": SECRET_VALUE}
        result = subprocess.run(
            [sys.executable, "-I", "-c", SCRIPT.read_text(encoding="utf-8"), "--stdin"],
            input=json.dumps(payload), capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr[-300:])
        self.assertIn("Only a local development Keycloak is accepted", result.stderr)
        self.assertNotIn(SECRET_VALUE, result.stdout + result.stderr)

    def file_client(self, client_id):
        return next(client for client in self.file["clients"] if client["clientId"] == client_id)

    def file_scope(self, name):
        return next(scope for scope in self.file["clientScopes"] if scope["name"] == name)


@unittest.skipUnless(live_available(), "Keycloak development environment is required")
class MobileTokenLiveTest(unittest.TestCase):
    """D-6: the real mobile-app client gets a token for site-tenant1 with the mobile scope (report check 5a)."""

    def test_real_mobile_client_gets_mobile_token_for_site_tenant1(self):
        from test_token_access_matrix import TokenAccessMatrixTest, audiences

        matrix = TokenAccessMatrixTest("test_browser_code_exchange_binds_id_token_to_the_requesting_client")
        matrix.setUp()
        opener = matrix.open_tenant_session()
        tokens = matrix.browser_token(opener, "mobile-app", "openid mobile aud-site-tenant1")
        self.assertIsNotNone(tokens, "Keycloak refused the mobile and aud-site-tenant1 scopes (invalid_scope).")
        claims = jwt_payload(tokens["access_token"])
        self.assertEqual(claims.get("azp"), "mobile-app")
        self.assertEqual(audiences(claims), {"site-tenant1"})
        self.assertIn("mobile", claims.get("scope", "").split())


if __name__ == "__main__":
    unittest.main()
