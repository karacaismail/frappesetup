"""Testlerin sahte HTTP sunucusu.

Sunucu Keycloak, Press ve kiracı sitesi yerine geçer. Gelen her isteği kaydeder.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlsplit

ISSUER_REALM = "platform"
# Keycloak realm'in iç kimliği. Addan farklıdır.
REALM_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
SUBJECT = "11111111-1111-4111-8111-111111111111"
ORG_ID = "22222222-2222-4222-8222-222222222222"


@dataclass
class Recorded:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes

    def json(self) -> object:
        return json.loads(self.body.decode("utf-8"))

    def form(self) -> dict[str, list[str]]:
        return parse_qs(self.body.decode("utf-8"))


Reply = tuple[int, object]
Route = Callable[[Recorded], Reply]


@dataclass
class FakeServer:
    """Kayıtlı yollara yanıt veren küçük sunucu."""

    routes: dict[tuple[str, str], Route] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)

    def __post_init__(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self) -> None:
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                recorded = Recorded(
                    method=self.command,
                    path=parts.path,
                    query=parse_qs(parts.query),
                    headers={k.lower(): v for k, v in self.headers.items()},
                    body=self.rfile.read(length) if length else b"",
                )
                owner.requests.append(recorded)
                route = owner.routes.get((self.command, parts.path))
                reply = route(recorded) if route else (404, {"error": "no route"})
                status, body = reply[0], reply[1]
                extra = reply[2] if len(reply) > 2 else {}
                raw = b"" if body is None else json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for name, value in extra.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_PUT = do_DELETE = _serve

            def log_message(self, *args: object) -> None:  # testte gürültü yapmasın
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def on(self, method: str, path: str, reply: Reply | Route) -> None:
        self.routes[(method, path)] = reply if callable(reply) else (lambda _req: reply)

    def calls(self, method: str, path: str) -> list[Recorded]:
        return [r for r in self.requests if r.method == method and r.path == path]

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


def keycloak_user(
    *,
    subject: str = SUBJECT,
    email: str = "ayse@example.test",
    verified: bool = True,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "id": subject,
        "username": email,
        "email": email,
        "emailVerified": verified,
        "enabled": enabled,
        "firstName": "Ayşe",
        "lastName": "Örnek",
    }


class FakeKeycloak(FakeServer):
    """Belirteç ucunu ve Admin API'nin kullanılan parçasını taklit eder."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.users: dict[str, dict[str, object]] = {}
        self.memberships: dict[str, list[dict[str, object]]] = {}
        self.organizations: dict[str, dict[str, object]] = {}
        self.on("POST", f"/realms/{ISSUER_REALM}/protocol/openid-connect/token", self._token)
        self.on("GET", f"/admin/realms/{ISSUER_REALM}/users/count", lambda _r: (200, len(self.users)))

    @property
    def admin(self) -> str:
        return f"/admin/realms/{ISSUER_REALM}"

    def _token(self, req: Recorded) -> Reply:
        scope = (req.form().get("scope") or [""])[0]
        return 200, {"access_token": f"token-for:{scope}", "expires_in": 300, "token_type": "Bearer"}

    def add_user(self, user: dict[str, object], organizations: list[dict[str, object]] | None = None) -> None:
        subject = str(user["id"])
        self.users[subject] = user
        self.memberships[subject] = list(organizations or [])
        self.on("GET", f"{self.admin}/users/{subject}", lambda _r: self._user(subject))
        self.on(
            "GET",
            f"{self.admin}/organizations/members/{subject}/organizations",
            lambda _r: (200, self.memberships.get(subject, [])),
        )

    def _user(self, subject: str) -> Reply:
        user = self.users.get(subject)
        return (200, user) if user else (404, {"error": "User not found"})

    def remove_user(self, subject: str) -> None:
        self.users.pop(subject, None)
        self.memberships.pop(subject, None)
        self.on("GET", f"{self.admin}/users/{subject}", (404, {"error": "User not found"}))
        self.on(
            "GET",
            f"{self.admin}/organizations/members/{subject}/organizations",
            (404, {"error": "User not found"}),
        )

    def add_organization(self, org_id: str, alias: str) -> dict[str, object]:
        org = {"id": org_id, "name": alias, "alias": alias}
        self.organizations[org_id] = org
        self.on("GET", f"{self.admin}/organizations/{org_id}", (200, org))
        return org


TENANT = "kiraci1"
PRESS_ENSURE_TEAM = "/api/method/press_tr.api.identity.ensure_team"
PRESS_REMOVE_MEMBER = "/api/method/press_tr.api.identity.remove_team_member"
PRESS_LIST = "/api/method/press_tr.api.identity.list_identities"
TENANT_PROVISION = "/api/method/platform_core.api.identity.provision"
TENANT_SET_ENABLED = "/api/method/platform_core.api.identity.set_enabled"
TENANT_CHANGE_EMAIL = "/api/method/platform_core.api.identity.change_email"
TENANT_LIST = "/api/method/platform_core.api.identity.list_identities"
WEBHOOK_SECRET = "test-webhook-secret"
# Hedef uçların kesin başarı yanıtı (`contracts/identity_sync.openapi.yaml`, TargetWriteResult).
DONE = (200, {"message": {"status": "done"}})
# `ensure_team` yanıtı (`docs/sozlesmeler.md`, "Kuruluş ile takım eşlemesi").
TEAM_READY = (200, {"message": {"team": "team-0001", "created": True}})


class FakeSite(FakeServer):
    """Press ya da kiracı sitesi. Bilinen bütün yazma uçlarına başarı döner."""

    def __post_init__(self) -> None:
        super().__post_init__()
        for path in (
            PRESS_ENSURE_TEAM,
            PRESS_REMOVE_MEMBER,
            TENANT_PROVISION,
            TENANT_SET_ENABLED,
            TENANT_CHANGE_EMAIL,
        ):
            self.on("POST", path, TEAM_READY if path == PRESS_ENSURE_TEAM else DONE)

    def writes(self) -> list[Recorded]:
        return [r for r in self.requests if r.method != "GET"]


def make_settings(keycloak: FakeServer, press: FakeServer, tenant: FakeServer, db_path: str, tenant2=None):
    from identity_sync.config import Settings
    from identity_sync.mapping import Tenant

    tenants = [Tenant(name=TENANT, base_url=tenant.url, organization=TENANT)]
    if tenant2 is not None:
        tenants.append(Tenant(name="kiraci2", base_url=tenant2.url, organization="kiraci2"))
    return Settings(
        keycloak_public_url=keycloak.url,
        realm=ISSUER_REALM,
        client_id="identity-sync",
        client_secret="test-client-secret",
        press_url=press.url,
        tenants=tuple(tenants),
        webhook_secret=WEBHOOK_SECRET,
        db_path=db_path,
        admin_scope="admin-api",
        http_timeout=5.0,
        realm_id=REALM_ID,
        execute_azp=frozenset({"approval-service"}),
        preview_azp=frozenset({"ai-agent"}),
    )


class Stack:
    """Üç sahte sunucuyu ve servisi birlikte kurar."""

    def __init__(self, db_path: str = ":memory:", *, two_tenants: bool = False) -> None:
        from identity_sync.app import build_app

        self.keycloak = FakeKeycloak()
        self.press = FakeSite()
        self.tenant = FakeSite()
        self.tenant2 = FakeSite() if two_tenants else None
        self.settings = make_settings(self.keycloak, self.press, self.tenant, db_path, self.tenant2)
        self.sleeps: list[float] = []
        self.app = build_app(self.settings, sleep=self.sleeps.append)

    @property
    def issuer(self) -> str:
        return f"{self.keycloak.url}/realms/{ISSUER_REALM}"

    def close(self) -> None:
        self.app.close()
        for server in (self.keycloak, self.press, self.tenant, self.tenant2):
            if server is not None:
                server.close()
