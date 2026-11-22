"""Access matrix: every endpoint against every kind of caller, over real HTTP (D-6).

Rows are the endpoints of the contract. Columns are the callers:

- no credential,
- a client that is not in any list,
- a listed client without the right for this endpoint ("wrong azp"),
- a token for another audience ("wrong aud"),
- an expired token,
- the client of another tenant,
- the right client.

`AccessMatrixTest` runs with a stand-in verifier, so it runs everywhere. It cannot build a
token with a wrong audience or an expired one. `RealTokenMatrixTest` runs the same rows with
real RS256 tokens and the real `oidc_verify` library, and adds those two columns.

The table in README.md ("Yetki tablosu") is this matrix.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from identity_sync.auth import TokenRejected, build_verifier
from identity_sync.server import make_server

from . import fakes
from .fakes import ORG_ID, SUBJECT, Stack, keycloak_user
from .test_auth import CERTS_PATH, HAVE_LIBRARY
from .test_server import NOW, sign

SITE, OTHER_SITE, AGENT, PRESS = "site-tenant1-service", "site-tenant2-service", "ai-agent", "press-service"
# The browser login client of the same tenant. It has no service account (docs/sozlesmeler.md, section 2).
OPERATOR = "identity-sync-operator"
BROWSER = "site-tenant1"
SID = "55555555-5555-4555-8555-555555555555"
STALE = {"dry_run": False, "preview_digest": "0" * 64, "approval_id": "onay-x1"}
INVITATION = {"email": "davetli@example.test", "organization_id": ORG_ID}


@dataclasses.dataclass(frozen=True)
class Row:
    """One endpoint in one mode. `right` reaches the handler; its status shows that.

    `wrong_azp` is a listed client without the right. `other_tenant` is the status for the
    client of another tenant; `None` means the endpoint is not bound to a tenant.
    """

    name: str
    method: str
    path: str
    body: object
    right: str
    right_status: int
    wrong_azp: str
    other_tenant: int | None = 403


ROWS = (
    Row("reconcile preview", "POST", "/v1/reconcile", {"dry_run": True}, OPERATOR, 200, AGENT),
    Row("reconcile execute", "POST", "/v1/reconcile", STALE, OPERATOR, 409, AGENT),
    Row("dead-letters list", "GET", "/v1/dead-letters", None, OPERATOR, 200, AGENT),
    Row("replay preview", "POST", "/v1/dead-letters/replay", {"dry_run": True}, OPERATOR, 200, AGENT),
    Row("replay execute", "POST", "/v1/dead-letters/replay", STALE, OPERATOR, 409, AGENT),
    Row("operations list", "GET", "/v1/operations", None, OPERATOR, 200, AGENT),
    Row("operation resolve", "POST", "/v1/operations/o-1/resolve", {"resolution": "abandoned"}, SITE, 200, AGENT),
    Row("invitation preview", "POST", "/v1/invitations", {**INVITATION, "dry_run": True}, SITE, 200, PRESS, 403),
    Row("invitation execute", "POST", "/v1/invitations", {**INVITATION, **STALE}, SITE, 409, AGENT, 403),
    Row("session revoke", "POST", "/v1/sessions/revoke", {"sid": SID, "subject": SUBJECT}, SITE, 200, AGENT, 403),
    Row("account deletion", "POST", "/v1/account-deletions", None, PRESS, 200, SITE, 403),
)


class MatrixCase(unittest.TestCase):
    """Shared setup. Subclasses say how a credential for a client is made."""

    def setUp(self) -> None:
        self.stack = Stack(two_tenants=True)
        self.addCleanup(self.stack.close)
        sites = frozenset({SITE, OTHER_SITE})
        # docs/sozlesmeler.md, section 7: the tenant site clients execute and end sessions.
        self.stack.app.settings = dataclasses.replace(
            self.stack.app.settings,
            preview_azp=frozenset({AGENT}),
            operator_azp=frozenset({OPERATOR}),
            execute_azp=sites,
            session_azp=sites,
            deletion_azp=frozenset({PRESS}),
        )
        self.stack.app.store.operation_begin("o-1", "invite_user", ORG_ID, ["create_user"])
        keycloak = self.stack.keycloak
        org = keycloak.add_organization(ORG_ID, "tenant1")
        keycloak.add_user(keycloak_user(), [org])
        keycloak.add_session(SUBJECT, SID)
        keycloak.serve_directory()
        keycloak.on("GET", f"{keycloak.admin}/users", (200, []))
        self.now = float(NOW)

    def serve(self, verifier) -> None:
        self.httpd = make_server(
            self.stack.app, verifier, host="127.0.0.1", port=0, request_timeout=2.0, clock=lambda: self.now
        )
        thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def body_of(self, row: Row) -> bytes | None:
        if row.name == "account deletion":
            return json.dumps({"issuer": self.stack.issuer, "subject": SUBJECT, "reauthenticated_at": int(self.now) - 10}).encode()
        return None if row.body is None else json.dumps(row.body).encode()

    def send(self, row: Row, authorization: str | None, headers: dict[str, str] | None = None) -> int:
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        if authorization is not None:
            all_headers["Authorization"] = authorization
        request = urllib.request.Request(self.base + row.path, data=self.body_of(row), method=row.method, headers=all_headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            with error:
                return error.code

    def writes(self) -> int:
        keycloak = [r for r in self.stack.keycloak.requests if r.method != "GET" and "/admin/" in r.path]
        return len(self.stack.press.writes() + self.stack.tenant.writes() + keycloak)

    def credential(self, azp: str) -> str:
        raise NotImplementedError

    def make_verifier(self):
        raise NotImplementedError

    def serve_again(self) -> None:
        """Start a second server that reads the settings as they are now."""
        self.serve(self.make_verifier())

    # --- the columns every verifier can test ---

    def check(self, column: str, authorization_of, expected_of) -> None:
        for row in ROWS:
            with self.subTest(column=column, row=row.name):
                expected = expected_of(row)
                if expected is None:
                    continue
                before = self.writes()
                self.assertEqual(self.send(row, authorization_of(row)), expected)
                if expected in (401, 403):
                    self.assertEqual(self.writes(), before)  # a refused caller writes nothing

    def run_common_columns(self) -> None:
        self.check("no credential", lambda row: None, lambda row: 401)
        self.check("not a bearer", lambda row: "Basic dXNlcjpwYXNz", lambda row: 401)
        self.check("unlisted client", lambda row: self.credential("stranger"), lambda row: 401)
        # A token whose `azp` is the tenant's browser client is refused on every endpoint.
        self.check("browser client", lambda row: self.credential(BROWSER), lambda row: 401)
        self.check("wrong azp", lambda row: self.credential(row.wrong_azp), lambda row: 403)
        self.check("other tenant", lambda row: self.credential(OTHER_SITE), lambda row: row.other_tenant)
        self.check("right client", lambda row: self.credential(row.right), lambda row: row.right_status)

    def test_browser_client_is_not_a_tenant_even_when_someone_lists_it(self) -> None:
        # Defence in depth. The settings refuse a browser client in a list. If a list held it
        # anyway, the service would still not take it for the tenant: only the service client
        # of a tenant maps to that tenant.
        if type(self) is MatrixCase:
            self.skipTest("the shared base has no verifier; the two subclasses run this test")
        settings = self.stack.app.settings
        self.stack.app.settings = dataclasses.replace(settings, session_azp=settings.session_azp | {BROWSER})
        self.serve_again()
        row = next(row for row in ROWS if row.name == "session revoke")

        self.assertEqual(self.send(row, self.credential(BROWSER)), 403)
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [SID])
        self.assertEqual(self.send(row, self.credential(SITE)), 200)

    def test_listed_client_without_a_tenant_cannot_execute_anything(self) -> None:
        # Defence in depth. The settings refuse such a list. If a list held a client that is
        # bound to no configured tenant, the service would still refuse to execute for it:
        # it could not tell whose organization the work belongs to.
        if type(self) is MatrixCase:
            self.skipTest("the shared base has no verifier; the two subclasses run this test")
        unbound = "approval-service"
        settings = self.stack.app.settings
        self.stack.app.settings = dataclasses.replace(
            settings, execute_azp=settings.execute_azp | {unbound}, session_azp=settings.session_azp | {unbound}
        )
        self.serve_again()
        before = self.writes()
        for row in ROWS:
            if row.right != SITE:
                continue
            with self.subTest(row=row.name):
                self.assertEqual(self.send(row, self.credential(unbound)), 403)
        self.assertEqual(self.writes(), before)
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [SID])

    def test_matrix_covers_every_token_endpoint_of_the_contract(self) -> None:
        from .test_contract import CONTRACT

        token_paths = {
            (method.upper(), path if "{" not in path else "/v1/operations/o-1/resolve")
            for path, item in CONTRACT["paths"].items()
            for method, operation in item.items()
            if method in ("get", "post") and operation.get("security") == [{"serviceToken": []}]
        }
        self.assertEqual({(row.method, row.path) for row in ROWS}, token_paths)


class AccessMatrixTest(MatrixCase):
    def setUp(self) -> None:
        super().setUp()
        self.serve(self.make_verifier())

    def make_verifier(self):
        listed = self.stack.app.settings.known_azp

        def verifier(token: str) -> dict[str, object]:
            azp = token.removeprefix("token-of-")
            if azp not in listed:
                raise TokenRejected("unknown_client")
            return {"azp": azp}

        return verifier

    def credential(self, azp: str) -> str:
        return f"Bearer token-of-{azp}"

    def test_every_endpoint_against_every_caller(self) -> None:
        self.run_common_columns()

    def test_health_check_needs_no_credential(self) -> None:
        health = Row("health", "GET", "/healthz", None, OPERATOR, 200, AGENT)
        for authorization in (None, self.credential("stranger"), self.credential(AGENT)):
            self.assertEqual(self.send(health, authorization), 200)

    def test_event_endpoint_takes_a_signature_and_no_token(self) -> None:
        event = {"id": "e-1", "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 1, "user_id": SUBJECT}
        row = Row("events", "POST", "/v1/events", event, AGENT, 202, PRESS)
        body = json.dumps(event).encode()
        stamp = str(int(self.now))
        good = {"X-Identity-Sync-Timestamp": stamp, "X-Identity-Sync-Signature": sign(body, int(self.now))}
        bad = {**good, "X-Identity-Sync-Signature": "sha256=" + "0" * 64}
        old = {"X-Identity-Sync-Timestamp": str(int(self.now) - 301), "X-Identity-Sync-Signature": sign(body, int(self.now) - 301)}

        self.assertEqual(self.send(row, None), 401)
        # A service token is not a signature, whoever it belongs to.
        for azp in (AGENT, SITE, PRESS):
            self.assertEqual(self.send(row, self.credential(azp)), 401)
        self.assertEqual(self.send(row, None, bad), 401)
        self.assertEqual(self.send(row, None, old), 401)
        self.assertEqual(self.writes(), 0)
        self.assertEqual(self.send(row, None, good), 202)
        # The same signature works once.
        self.assertEqual(self.send(row, None, good), 401)


@unittest.skipUnless(HAVE_LIBRARY, "the oidc_verify library is not installed")
class RealTokenMatrixTest(MatrixCase):
    """The same rows with real RS256 tokens, checked by the real library."""

    @classmethod
    def setUpClass(cls) -> None:
        from cryptography.hazmat.primitives.asymmetric import rsa

        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self) -> None:
        super().setUp()
        from .test_auth import _b64

        numbers = self.key.public_key().public_numbers()
        key = {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "k1", "n": _b64(numbers.n), "e": _b64(numbers.e)}
        self.stack.keycloak.on("GET", CERTS_PATH, (200, {"keys": [key]}))
        self.now = time.time()  # the library reads the real clock
        self.serve(self.make_verifier())

    def make_verifier(self):
        return build_verifier(self.stack.app.settings)

    def credential(self, azp: str, *, key=None, **claims: object) -> str:
        import jwt

        now = int(time.time())
        payload = {"iss": self.stack.issuer, "aud": "identity-sync", "azp": azp, "sub": f"service-account-{azp}", "iat": now, "exp": now + 300}
        payload.update(claims)
        return "Bearer " + jwt.encode(payload, key or self.key, algorithm="RS256", headers={"kid": "k1"})

    def test_every_endpoint_against_every_caller(self) -> None:
        self.run_common_columns()

    def test_right_client_with_a_bad_token_is_refused_everywhere(self) -> None:
        now = int(time.time())
        columns = {
            "wrong aud": {"aud": "press"},
            "aud of a tenant site": {"aud": "site-tenant1"},
            "two audiences": {"aud": ["identity-sync", "press"]},
            "expired": {"iat": now - 600, "exp": now - 300},
            "wrong issuer": {"iss": "http://baska.example.test/realms/platform"},
        }
        for column, claims in columns.items():
            self.check(column, lambda row, claims=claims: self.credential(row.right, **claims), lambda row: 401)
        self.check("wrong key", lambda row: self.credential(row.right, key=self.other_key), lambda row: 401)
