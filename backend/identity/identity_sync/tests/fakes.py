"""Fake HTTP servers for the tests.

The servers stand in for Keycloak, Press and the tenant site. They record every request.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlsplit

ISSUER_REALM = "platform"
# The internal Keycloak realm ID, distinct from its name.
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


@dataclass(frozen=True)
class Trickle:
    """A reply body sent in small pieces with a pause after each piece, like a slow target."""

    body: object
    piece: int = 4
    pause: float = 0.1


@dataclass
class FakeServer:
    """A small server that responds to registered routes."""

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
                denied = owner.authorize(recorded)
                if denied is not None:
                    reply = denied
                else:
                    reply = route(recorded) if route else (404, {"error": "no route"})
                if reply is DONE:
                    # A test route asked for the site's own contract behaviour.
                    reply = owner._defaults[(self.command, parts.path)](recorded)
                status, body = reply[0], reply[1]
                if status == 0:
                    self.close_connection = True
                    self.connection.close()
                    return
                extra = reply[2] if len(reply) > 2 else {}
                trickle = body if isinstance(body, Trickle) else None
                if trickle is not None:
                    body = trickle.body
                if isinstance(body, str):
                    raw = body.encode("utf-8")  # a non-JSON body
                else:
                    raw = b"" if body is None else json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for name, value in extra.items():
                    self.send_header(name, value)
                try:
                    self.end_headers()
                    if trickle is None:
                        self.wfile.write(raw)
                    for start in range(0, len(raw), trickle.piece) if trickle else ():
                        self.wfile.write(raw[start:start + trickle.piece])
                        self.wfile.flush()
                        time.sleep(trickle.pause)
                except (BrokenPipeError, ConnectionResetError):
                    return  # the client gave up waiting, for example after its timeout

            do_GET = do_POST = do_PUT = do_DELETE = _serve

            def log_message(self, *args: object) -> None:  # keep test output quiet
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def authorize(self, _req: Recorded) -> Reply | None:
        """Return an error reply to refuse the request, or None to let it through."""
        return None

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


ADMIN_SCOPE = "admin-api kc-admin-api"
# Roles the identity-sync service account carries (docs/sozlesmeler.md, section 2). They reach only
# a token requested with ADMIN_SCOPE. `manage-clients` is not among them.
# Ending a session needs manage-users (Keycloak: RealmAdminResource.deleteSession).
ADMIN_ROLE_PATHS = ("/users", "/organizations", "/sessions")


class FakeKeycloak(FakeServer):
    """Simulate the token endpoint and the subset of the Admin API used by the service.

    The Admin API answers 403 unless the token was requested with ADMIN_SCOPE and the path
    is covered by the service account's roles.
    """

    def __post_init__(self) -> None:
        self.extra_role_paths: tuple[str, ...] = ()
        super().__post_init__()
        self.users: dict[str, dict[str, object]] = {}
        self.memberships: dict[str, list[dict[str, object]]] = {}
        self.organizations: dict[str, dict[str, object]] = {}
        self.logged_out: list[str] = []
        self.sessions: dict[str, list[str]] = {}
        self.on("POST", f"/realms/{ISSUER_REALM}/protocol/openid-connect/token", self._token)
        self.on("GET", f"/admin/realms/{ISSUER_REALM}/users/count", lambda _r: (200, len(self.users)))

    @property
    def admin(self) -> str:
        return f"/admin/realms/{ISSUER_REALM}"

    def authorize(self, req: Recorded) -> Reply | None:
        prefix = self.admin
        if not req.path.startswith(prefix):
            return None
        if req.headers.get("authorization") != f"Bearer token-for:{ADMIN_SCOPE}":
            return 403, {"error": "HTTP 403 Forbidden"}
        if not req.path[len(prefix) :].startswith(ADMIN_ROLE_PATHS + self.extra_role_paths):
            return 403, {"error": "HTTP 403 Forbidden"}
        return None

    def _token(self, req: Recorded) -> Reply:
        scope = (req.form().get("scope") or [""])[0]
        return 200, {"access_token": f"token-for:{scope}", "expires_in": 300, "token_type": "Bearer"}

    def add_user(self, user: dict[str, object], organizations: list[dict[str, object]] | None = None) -> None:
        subject = str(user["id"])
        self.users[subject] = user
        self.memberships[subject] = list(organizations or [])
        self.on("GET", f"{self.admin}/users/{subject}", lambda _r: self._user(subject))
        self.on("PUT", f"{self.admin}/users/{subject}", lambda req: self._update_user(subject, req))
        self.on("POST", f"{self.admin}/users/{subject}/logout", lambda _r: self._logout(subject))
        self.on("DELETE", f"{self.admin}/users/{subject}", lambda _r: self._delete_user(subject))
        self.on("GET", f"{self.admin}/users/{subject}/sessions", lambda _r: self._sessions(subject))
        self.on(
            "GET",
            f"{self.admin}/organizations/members/{subject}/organizations",
            lambda _r: (200, self.memberships.get(subject, [])),
        )

    def add_session(self, subject: str, session_id: str) -> None:
        """Give the user an active session. Keycloak lists it and can delete it."""
        self.sessions.setdefault(subject, []).append(session_id)
        self.on("DELETE", f"{self.admin}/sessions/{session_id}", lambda _r: self._delete_session(session_id))

    def _sessions(self, subject: str) -> Reply:
        if subject not in self.users:
            return 404, {"error": "User not found"}
        return 200, [{"id": session_id, "userId": subject} for session_id in self.sessions.get(subject, [])]

    def _delete_session(self, session_id: str) -> Reply:
        for sessions in self.sessions.values():
            if session_id in sessions:
                sessions.remove(session_id)
                return 204, None
        return 404, {"error": "Session not found"}

    def _update_user(self, subject: str, req: Recorded) -> Reply:
        if subject not in self.users:
            return 404, {"error": "User not found"}
        self.users[subject] = {**self.users[subject], **req.json()}
        return 204, None

    def _logout(self, subject: str) -> Reply:
        if subject not in self.users:
            return 404, {"error": "User not found"}
        self.logged_out.append(subject)
        return 204, None

    def _delete_user(self, subject: str) -> Reply:
        if self.users.pop(subject, None) is None:
            return 404, {"error": "User not found"}
        self.memberships.pop(subject, None)
        return 204, None

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

    def serve_directory(self) -> None:
        """Serve the user list, the organization list and the member lists from the fake's state."""

        def page(rows: list, req: Recorded) -> Reply:
            first, size = int(req.query.get("first", ["0"])[0]), int(req.query.get("max", ["100"])[0])
            return 200, rows[first : first + size]

        organizations: dict[str, dict[str, object]] = {}
        for memberships in self.memberships.values():
            for org in memberships:
                organizations[str(org["id"])] = org
        self.on("GET", f"{self.admin}/users", lambda req: page(list(self.users.values()), req))
        self.on("GET", f"{self.admin}/organizations", lambda req: page(list(organizations.values()), req))
        for org_id in organizations:
            members = [
                self.users[subject]
                for subject, memberships in self.memberships.items()
                if any(org["id"] == org_id for org in memberships)
            ]
            self.on("GET", f"{self.admin}/organizations/{org_id}/members", lambda req, members=members: page(members, req))

    def add_organization(self, org_id: str, alias: str) -> dict[str, object]:
        org = {"id": org_id, "name": alias, "alias": alias}
        self.organizations[org_id] = org
        self.on("GET", f"{self.admin}/organizations/{org_id}", (200, org))
        return org


TENANT = "tenant1"
PRESS_ENSURE_TEAM = "/api/method/press_tr.api.identity.ensure_team"
PRESS_REMOVE_MEMBER = "/api/method/press_tr.api.identity.remove_team_member"
PRESS_LIST = "/api/method/press_tr.api.identity.list_identities"
TENANT_PROVISION = "/api/method/platform_core.api.identity.provision"
TENANT_SET_ENABLED = "/api/method/platform_core.api.identity.set_enabled"
TENANT_CHANGE_EMAIL = "/api/method/platform_core.api.identity.change_email"
TENANT_LIST = "/api/method/platform_core.api.identity.list_identities"
# Proposed target endpoints. They are not in the tenant or Press contracts yet.
# The fakes follow the Target schemas in contracts/identity_sync.openapi.yaml.
TENANT_REVOKE_INSTALLATIONS = "/api/method/platform_core.api.mobile.revoke_user_installations"
TENANT_ANONYMIZE = "/api/method/platform_core.api.identity.anonymize_user"
PRESS_ANONYMIZE = "/api/method/press_tr.api.identity.anonymize_user"
ANONYMOUS = "anonymized"
WEBHOOK_SECRET = "test-webhook-secret"
# Made at run time, so no key-shaped constant sits in the repository. One value per test run.
DIGEST_KEY = secrets.token_hex(16)
# Sentinel: passing DONE to FakeSite.on() restores the site's own contract behaviour for that path.
DONE = (-1, None)
# The server reads the request, then closes the connection without answering.
DROP = (0, None)
WEBSITE_USER = "Website User"


def frappe_error(status: int, exc_type: str) -> Reply:
    """Frappe's usual error body. The client recognises the error by `exc_type`."""
    return status, {"exc_type": exc_type, "exception": f"{exc_type}: rejected"}


def _has_only(body: object, required: set[str], optional: set[str]) -> bool:
    """`additionalProperties: false` plus `required`, as both target contracts demand."""
    return isinstance(body, dict) and required <= set(body) <= required | optional


class FakeSite(FakeServer):
    """Base for the two fake targets. A test may override a path and later restore it with DONE."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self._defaults: dict[tuple[str, str], Route] = {}

    def default(self, method: str, path: str, route: Route) -> None:
        self._defaults[(method, path)] = route
        self.routes[(method, path)] = route

    def on(self, method: str, path: str, reply: Reply | Route) -> None:
        if reply is DONE:
            self.routes[(method, path)] = self._defaults[(method, path)]
        else:
            super().on(method, path, reply)

    def writes(self) -> list[Recorded]:
        return [r for r in self.requests if r.method != "GET"]


def paged_identities(req: Recorded, rows: list[dict[str, object]]) -> Reply:
    """`list_identities` as docs/sozlesmeler.md, section 7 defines it.

    The request takes `start` (default 0) and `page_length` (default 500, at most 500).
    The order is `subject`, ascending. The reply is `{"identities": [...], "has_next_page": bool}`.
    """
    start = int(req.query.get("start", ["0"])[0])
    page_length = int(req.query.get("page_length", ["500"])[0])
    if start < 0 or not 1 <= page_length <= 500:
        return frappe_error(400, "ValidationError")
    ordered = sorted(rows, key=lambda row: str(row["subject"]))
    page = ordered[start : start + page_length]
    return 200, {"message": {"identities": page, "has_next_page": start + page_length < len(ordered)}}


class FakeTenant(FakeSite):
    """A tenant site that behaves like `contracts/platform_core-kimlik.openapi.yaml` (0.2.0).

    Source of the behaviour: that contract and `platform_core/identity/provisioning.py`.
    State: identity links `(issuer, subject) -> user` and users keyed by e-mail.
    """

    def __post_init__(self) -> None:
        super().__post_init__()
        self.links: dict[tuple[str, str], str] = {}
        self.users: dict[str, dict[str, object]] = {}
        self.default("POST", TENANT_PROVISION, self._provision)
        self.default("POST", TENANT_SET_ENABLED, self._set_enabled)
        self.default("POST", TENANT_CHANGE_EMAIL, self._change_email)
        self.default("GET", TENANT_LIST, self._list)
        self.installations: dict[tuple[str, str], list[str]] = {}
        self.default("POST", TENANT_REVOKE_INSTALLATIONS, self._revoke_installations)
        self.default("POST", TENANT_ANONYMIZE, self._anonymize)

    def _identity(self, req: Recorded) -> tuple[tuple[str, str] | None, Reply | None]:
        body = req.json()
        if not _has_only(body, {"issuer", "subject"}, set()):
            return None, frappe_error(400, "InvalidInput")
        key = (body["issuer"], body["subject"])
        if key not in self.links:
            return None, frappe_error(404, "IdentityNotFound")
        return key, None

    def _revoke_installations(self, req: Recorded) -> Reply:
        key, error = self._identity(req)
        if error:
            return error
        revoked = len(self.installations.pop(key, []))
        return 200, {"message": {"revoked": revoked}}

    def _anonymize(self, req: Recorded) -> Reply:
        key, error = self._identity(req)
        if error:
            if error[0] == 404:
                # O-43: an identity the tenant does not know gets 200 with `found` false, never 404.
                return 200, {"message": {"anonymized": True, "found": False}}
            return error
        # Personal fields are blanked. The record itself stays: business records are not deleted.
        self.users[self.links[key]].update(first_name="", last_name="", anonymized=True, enabled=False)
        # Body from docs/sozlesmeler.md, section 6 ("anonymized" and "found"). The tenant follows the same rules.
        return 200, {"message": {"anonymized": True, "found": True}}

    def _list(self, _req: Recorded) -> Reply:
        rows = [
            {"issuer": issuer, "subject": subject, "enabled": self.users[email]["enabled"]}
            for (issuer, subject), email in self.links.items()
            # An anonymized record no longer carries the raw `sub` (docs/sozlesmeler.md, section 7).
            if not self.users[email].get("anonymized")
        ]
        return paged_identities(_req, rows)

    def seed_user(self, issuer: str, subject: str, email: str, *, enabled: bool = True) -> None:
        self.links[(issuer, subject)] = email
        self.users[email] = {"enabled": enabled, "first_name": "", "last_name": ""}

    def user_of(self, issuer: str, subject: str) -> dict[str, object] | None:
        email = self.links.get((issuer, subject))
        return None if email is None else {"email": email, **self.users[email]}

    def _provision(self, req: Recorded) -> Reply:
        body = req.json()
        required = {"issuer", "subject", "email", "email_verified", "enabled"}
        if not _has_only(body, required, {"first_name", "last_name", "role_profiles"}):
            return frappe_error(400, "InvalidInput")
        if not isinstance(body["email_verified"], bool) or not isinstance(body["enabled"], bool):
            return frappe_error(400, "InvalidInput")
        key = (body["issuer"], body["subject"])
        user = self.links.get(key)
        if user is not None:
            if user != body["email"]:
                return frappe_error(409, "EmailMismatch")
        else:
            if not body["email_verified"]:
                return frappe_error(409, "EmailNotVerified")
            if body["email"] in self.links.values():
                return frappe_error(409, "IdentityConflict")
            user = body["email"]
            self.links[key] = user
            self.users[user] = {}
        self.users[user].update(
            enabled=body["enabled"], first_name=body.get("first_name", ""), last_name=body.get("last_name", "")
        )
        message = {"user": user, "enabled": body["enabled"], "linked": True, "user_type": WEBSITE_USER}
        return 200, {"message": message}

    def _set_enabled(self, req: Recorded) -> Reply:
        body = req.json()
        if not _has_only(body, {"issuer", "subject", "enabled"}, set()) or not isinstance(body["enabled"], bool):
            return frappe_error(400, "InvalidInput")
        user = self.links.get((body["issuer"], body["subject"]))
        if user is None:
            return frappe_error(404, "IdentityNotFound")
        self.users[user]["enabled"] = body["enabled"]
        return 200, {"message": {"user": user, "enabled": body["enabled"]}}

    def _change_email(self, req: Recorded) -> Reply:
        body = req.json()
        if not _has_only(body, {"issuer", "subject", "new_email"}, set()):
            return frappe_error(400, "InvalidInput")
        key = (body["issuer"], body["subject"])
        user = self.links.get(key)
        if user is None:
            return frappe_error(404, "IdentityNotFound")
        new_email = body["new_email"]
        if user != new_email:
            if new_email in self.users:
                return frappe_error(409, "EmailInUse")
            self.users[new_email] = self.users.pop(user)
            self.links[key] = new_email
        return 200, {"message": {"user": new_email}}


class FakePress(FakeSite):
    """A Press site that behaves like `contracts/press_tr.openapi.yaml` (0.1.0).

    Source of the behaviour: that contract and docs/sozlesmeler.md, section 6.
    State: identity links, users with an `enabled` flag and API keys, and one team per organization.
    """

    def __post_init__(self) -> None:
        super().__post_init__()
        self.links: dict[tuple[str, str], str] = {}
        self.users: dict[str, dict[str, object]] = {}
        self.teams: dict[str, dict[str, object]] = {}
        self.default("POST", PRESS_ENSURE_TEAM, self._ensure_team)
        self.default("POST", PRESS_REMOVE_MEMBER, self._remove_team_member)
        self.default("GET", PRESS_LIST, self._list)
        self.default("POST", PRESS_ANONYMIZE, self._anonymize)

    def _anonymize(self, req: Recorded) -> Reply:
        body = req.json()
        if not _has_only(body, {"issuer", "subject"}, set()):
            return frappe_error(400, "ValidationError")
        email = self.links.get((body["issuer"], body["subject"]))
        if email is None:
            # docs/sozlesmeler.md, section 6: an unknown identity gets 200 with found false.
            return 200, {"message": {"anonymized": True, "found": False}}
        self.users[email].update(anonymized=True, enabled=False, api_keys=[])
        return 200, {"message": {"anonymized": True, "found": True}}

    def _list(self, _req: Recorded) -> Reply:
        rows = [
            # Only these three fields (docs/sozlesmeler.md, section 7). No e-mail, no name, no teams.
            {"issuer": issuer, "subject": subject, "enabled": self.users[email]["enabled"]}
            for (issuer, subject), email in self.links.items()
            if not self.users[email].get("anonymized")
        ]
        return paged_identities(_req, rows)

    def seed_member(self, issuer: str, subject: str, email: str, organization_id: str, *, api_keys: int = 0) -> None:
        self.links[(issuer, subject)] = email
        self.users[email] = {"enabled": True, "api_keys": [f"key-{n}" for n in range(api_keys)]}
        team = self.teams.setdefault(organization_id, {"name": f"team-{len(self.teams) + 1:04d}", "members": set()})
        team["members"].add(email)

    def user_of(self, issuer: str, subject: str) -> dict[str, object] | None:
        email = self.links.get((issuer, subject))
        return None if email is None else {"email": email, **self.users[email]}

    def teams_of(self, issuer: str, subject: str) -> list[str]:
        email = self.links.get((issuer, subject))
        return sorted(org for org, team in self.teams.items() if email in team["members"])

    def _ensure_team(self, req: Recorded) -> Reply:
        body = req.json()
        required = {"issuer", "subject", "email", "email_verified", "organization_id"}
        if not _has_only(body, required, {"organization_name"}) or not isinstance(body["email_verified"], bool):
            return frappe_error(400, "ValidationError")
        key = (body["issuer"], body["subject"])
        if key not in self.links:
            if not body["email_verified"]:
                return frappe_error(403, "PermissionError")
            self.links[key] = body["email"]
            self.users[body["email"]] = {"enabled": True, "api_keys": []}
        created = body["organization_id"] not in self.teams
        team = self.teams.setdefault(
            body["organization_id"], {"name": f"team-{len(self.teams) + 1:04d}", "members": set()}
        )
        team["members"].add(self.links[key])
        return 200, {"message": {"team": team["name"], "created": created}}

    def _remove_team_member(self, req: Recorded) -> Reply:
        body = req.json()
        if not _has_only(body, {"issuer", "subject"}, {"organization_id", "all_organizations"}):
            return frappe_error(400, "InvalidTeamSelector")
        has_org, has_all = "organization_id" in body, "all_organizations" in body
        org = body.get("organization_id")
        if has_org == has_all or (has_all and body["all_organizations"] is not True):
            return frappe_error(400, "InvalidTeamSelector")
        if has_org and (not isinstance(org, str) or not org.strip() or len(org) > 255):
            return frappe_error(400, "InvalidTeamSelector")
        email = self.links.get((body["issuer"], body["subject"]))
        if has_all:
            # Bulk removal also disables the linked user and revokes the API credentials.
            if email is not None:
                for team in self.teams.values():
                    team["members"].discard(email)
                self.users[email].update(enabled=False, api_keys=[])
            return 200, {"message": {"team": None, "member": False}}
        team = self.teams.get(org)
        if team is not None and email is not None:
            team["members"].discard(email)
        return 200, {"message": {"team": team["name"] if team else None, "member": False}}


def make_settings(keycloak: FakeServer, press: FakeServer, tenant: FakeServer, db_path: str, tenant2=None):
    from identity_sync.config import Settings
    from identity_sync.mapping import Tenant

    tenants = [Tenant(name=TENANT, base_url=tenant.url, organization=TENANT)]
    if tenant2 is not None:
        tenants.append(Tenant(name="tenant2", base_url=tenant2.url, organization="tenant2"))
    return Settings(
        keycloak_public_url=keycloak.url,
        realm=ISSUER_REALM,
        client_id="identity-sync",
        client_secret="test-client-secret",
        press_url=press.url,
        tenants=tuple(tenants),
        webhook_secret=WEBHOOK_SECRET,
        db_path=db_path,
        admin_scope=ADMIN_SCOPE,
        digest_key=DIGEST_KEY,
        http_timeout=5.0,
        realm_id=REALM_ID,
        # docs/sozlesmeler.md, section 7: both lists hold the service clients of the configured tenants.
        execute_azp=frozenset(f"site-{item.name}-service" for item in tenants),
        operator_azp=frozenset({"identity-sync-operator"}),
        preview_azp=frozenset({"ai-agent"}),
        session_azp=frozenset(f"site-{item.name}-service" for item in tenants),
        deletion_azp=frozenset({"press-service"}),
    )


class Stack:
    """Set up the three fake servers and the service together."""

    def __init__(self, db_path: str = ":memory:", *, two_tenants: bool = False, **settings: object) -> None:
        """`settings`: values that replace the test defaults, for example `anonymize_timeout`."""
        from dataclasses import replace

        from identity_sync.app import build_app

        self.keycloak = FakeKeycloak()
        self.press = FakePress()
        self.tenant = FakeTenant()
        self.tenant2 = FakeTenant() if two_tenants else None
        self.settings = replace(make_settings(self.keycloak, self.press, self.tenant, db_path, self.tenant2), **settings)
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
