"""Keycloak Admin API istemcisi.

Her işlev tek bir iş yapar ve açık bir ad taşır. Yazan her işlev `dry_run=True` ile
yalnız önizleme üretir. Servis Keycloak'ta istemci açmaz (`docs/sozlesmeler.md`, 7. bölüm).

Yolların kaynağı Keycloak 26.8.2 Admin REST API belgesidir.
Admin API belirteci ayrı kapsamla istenir. Bu belirteç sitelere gitmez.
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from identity_sync.httpjson import HttpError, Response, TransportError, request_json
from identity_sync.mapping import Organization, Preview, UserSnapshot
from identity_sync.tokens import TokenProvider

PAGE_SIZE = 100
INVITE_ACTIONS = ("UPDATE_PASSWORD", "CONFIGURE_TOTP")
TENANT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
SITE_BACKCHANNEL_LOGOUT_PATH = "/api/method/platform_core.api.keycloak_backchannel_logout"


@dataclass(frozen=True)
class Outcome:
    """Bir yazma işinin sonucu. `executed` yanlışsa yalnız önizleme üretildi."""

    preview: Preview
    executed: bool
    value: object = None


@dataclass(frozen=True)
class InviteResult:
    """`subject`, davet edilen kullanıcının kimliğidir. Önizlemede boş kalabilir."""

    subject: str | None
    previews: tuple[Preview, ...]


def site_client_id(tenant: str) -> str:
    if not TENANT_NAME.fullmatch(tenant):
        raise ValueError("invalid tenant name")
    return f"site-{tenant}"


def _quote(value: str) -> str:
    """Değeri adres yoluna güvenle koyar. Yolu değiştirebilen değeri reddeder."""
    if value in ("", ".", ".."):
        raise ValueError("invalid path segment")
    return urllib.parse.quote(value, safe="")


def _id_from_location(response: Response) -> str:
    location = response.headers.get("location", "")
    new_id = location.rstrip("/").rsplit("/", 1)[-1]
    if not new_id:
        raise TransportError("unexpected Keycloak response")
    return urllib.parse.unquote(new_id)


class PlanChanged(Exception):
    """Güncel plan onaylanan plandan farklı. Hiçbir şey yazılmadı."""


def _expect(response: Response, *statuses: int) -> Response:
    """Keycloak'ın yazma yanıtını denetler. Beklenmeyen durum kodu başarı sayılmaz."""
    if response.status not in statuses:
        raise TransportError("unexpected Keycloak response")
    return response


class KeycloakAdmin:
    def __init__(
        self, base_url: str, realm: str, tokens: TokenProvider, *, admin_scope: str = "", timeout: float = 10.0
    ) -> None:
        self._root = f"{base_url.rstrip('/')}/admin/realms/{_quote(realm)}"
        self._tokens = tokens
        self._admin_scope = admin_scope
        self._timeout = timeout

    # --- ortak yardımcılar ---

    def _call(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        json_body: object = None,
        has_body: bool = False,
    ) -> Response:
        return self._tokens.with_token(
            self._admin_scope,
            lambda token: request_json(
                method,
                f"{self._root}{path}",
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {token}"},
                query=query,
                json_body=json_body,
                has_body=has_body,
            ),
        )

    def _get_object_or_none(self, path: str) -> Mapping[str, object] | None:
        """Kaydı okur. Kayıt yoksa `None` döner.

        404 yanıtı tek başına "kayıt yok" kanıtı değildir. Yanlış realm adı ya da aradaki
        bir vekil sunucu da 404 döner. Bu yüzden işlev realm'in yanıt verdiğini ayrıca doğrular.
        Belirsiz yanıt hata sayılır. Çünkü "kullanıcı yok" sonucu kullanıcıyı her yerde kapatır.
        """
        try:
            body = self._call("GET", path).body
        except HttpError as error:
            if error.status != 404:
                raise
            self._confirm_realm_answers()
            return None
        if not isinstance(body, Mapping):
            raise TransportError("unexpected Keycloak response")
        return body

    def _confirm_realm_answers(self) -> None:
        count = self._call("GET", "/users/count").body
        if isinstance(count, bool) or not isinstance(count, int):
            raise TransportError("unexpected Keycloak response")

    def _list(self, path: str, *, query: Mapping[str, object] | None = None) -> list[Mapping[str, object]]:
        body = self._call("GET", path, query=query).body
        if not isinstance(body, list) or not all(isinstance(row, Mapping) for row in body):
            raise TransportError("unexpected Keycloak response")
        return body

    def _pages(self, path: str, *, query: Mapping[str, object] | None = None) -> Iterator[Mapping[str, object]]:
        first = 0
        while True:
            rows = self._list(path, query={**(query or {}), "first": first, "max": PAGE_SIZE})
            yield from rows
            if len(rows) < PAGE_SIZE:
                return
            first += PAGE_SIZE

    # --- okuma ---

    def get_user(self, subject: str) -> Mapping[str, object] | None:
        """Kullanıcının Keycloak gösterimini döner. Kullanıcı yoksa `None` döner."""
        user = self._get_object_or_none(f"/users/{_quote(subject)}")
        if user is None:
            return None
        if user.get("id") != subject or not isinstance(user.get("enabled"), bool):
            raise TransportError("unexpected Keycloak response")
        return user

    def find_user_by_email(self, email: str) -> Mapping[str, object] | None:
        for row in self._list("/users", query={"email": email, "exact": "true"}):
            if str(row.get("email", "")).lower() == email.lower():
                return row
        return None

    def list_users(self) -> Iterator[Mapping[str, object]]:
        """Realm'deki bütün kullanıcıları sayfa sayfa okur."""
        return self._pages("/users")

    def list_user_organizations(self, subject: str) -> tuple[Organization, ...]:
        """Kullanıcının üyeliklerini döner. Okunamayan üyelik "üyelik yok" sayılmaz, hata olur."""
        return tuple(_organization(row) for row in self._list(f"/organizations/members/{_quote(subject)}/organizations"))

    def get_user_snapshot(self, subject: str) -> UserSnapshot | None:
        """Kullanıcının güncel durumunu ve üyeliklerini birlikte döner."""
        user = self.get_user(subject)
        if user is None:
            return None
        if user.get("enabled") is not True:
            # A disabled account is closed everywhere. That plan needs no membership list,
            # so a failing membership read must not stop it.
            return snapshot_from_user(user, ())
        return snapshot_from_user(user, self.list_user_organizations(subject))

    def get_organization(self, organization_id: str) -> Organization | None:
        body = self._get_object_or_none(f"/organizations/{_quote(organization_id)}")
        return _organization(body) if body is not None else None

    def find_organization(self, name: str, alias: str) -> Organization | None:
        """Organization'ı adıyla arar. Yalnız takma adı da tutan kaydı döner.

        Keycloak arama ucu ada ve alan adına bakar. Takma ada bakmaz.
        """
        for row in self._list("/organizations", query={"search": name, "exact": "true"}):
            if row.get("alias") == alias:
                return _organization(row)
        return None

    def list_organizations(self) -> Iterator[Organization]:
        return (_organization(row) for row in self._pages("/organizations"))

    def list_organization_members(self, organization_id: str) -> Iterator[Mapping[str, object]]:
        return self._pages(f"/organizations/{_quote(organization_id)}/members")

    # --- yazma: her işlev tek iş yapar ---

    def create_organization(self, alias: str, name: str, *, dry_run: bool = False) -> Outcome:
        """Yeni bir Organization açar. Sonuç değeri yeni kimliktir."""
        preview = Preview(
            operation="keycloak.create_organization",
            target=alias,
            summary=f"Create Keycloak organization {alias}.",
            destructive=False,
        )
        if dry_run:
            return Outcome(preview, executed=False)
        response = self._call("POST", "/organizations", json_body={"name": name, "alias": alias, "enabled": True})
        return Outcome(preview, executed=True, value=_id_from_location(_expect(response, 201)))

    def add_organization_member(self, organization_id: str, subject: str, *, dry_run: bool = False) -> Outcome:
        """Kullanıcıyı Organization'a üye yapar. Kullanıcı zaten üyeyse iş yapmaz."""
        preview = Preview(
            operation="keycloak.add_organization_member",
            target=organization_id,
            summary=f"Add user {subject} to Keycloak organization {organization_id}.",
            destructive=False,
        )
        if dry_run:
            return Outcome(preview, executed=False)
        try:
            _expect(self._call("POST", f"/organizations/{_quote(organization_id)}/members", json_body=subject), 201, 204)
        except HttpError as error:
            if error.status != 409:  # 409: kullanıcı zaten üye
                raise
        return Outcome(preview, executed=True)

    def create_user(self, email: str, first_name: str, last_name: str, *, dry_run: bool = False) -> Outcome:
        """Parolasız ve e-postası doğrulanmamış bir kullanıcı açar. Sonuç değeri `sub` kimliğidir."""
        preview = Preview(
            operation="keycloak.create_user",
            target="keycloak",
            summary="Create a Keycloak user for the invited email address.",
            destructive=False,
        )
        if dry_run:
            return Outcome(preview, executed=False)
        body = {
            "username": email,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": False,
        }
        response = _expect(self._call("POST", "/users", json_body=body), 201)
        return Outcome(preview, executed=True, value=_id_from_location(response))

    def send_execute_actions_email(
        self,
        subject: str,
        actions: Sequence[str],
        *,
        client_id: str | None = None,
        redirect_uri: str | None = None,
        lifespan: int | None = None,
        dry_run: bool = False,
    ) -> Outcome:
        """Kullanıcıya `execute-actions-email` e-postası gönderir. Bu e-posta geri alınamaz."""
        preview = Preview(
            operation="keycloak.send_execute_actions_email",
            target=subject,
            summary=f"Email user {subject} a link to complete: {', '.join(actions)}.",
            destructive=False,
        )
        if dry_run:
            return Outcome(preview, executed=False)
        response = self._call(
            "PUT",
            f"/users/{_quote(subject)}/execute-actions-email",
            query={"client_id": client_id, "redirect_uri": redirect_uri, "lifespan": lifespan},
            json_body=list(actions),
        )
        _expect(response, 200, 204)
        return Outcome(preview, executed=True)

    def disable_user(self, subject: str) -> None:
        """Disable the user and end the user's sessions. Repeatable. A missing user counts as done.

        The full representation is sent back with `enabled` set to false, so no other field is lost.
        """
        user = self.get_user(subject)
        if user is None:
            return
        if user.get("enabled") is not False:
            _expect(self._call("PUT", f"/users/{_quote(subject)}", json_body={**user, "enabled": False}), 200, 204)
        _expect(self._call("POST", f"/users/{_quote(subject)}/logout"), 200, 204)

    def delete_user(self, subject: str) -> None:
        """Delete the user. This cannot be undone. Repeatable: a user that is already gone counts as done.

        A 404 alone does not prove that, because a wrong address answers 404 too, so the realm must answer.
        """
        try:
            _expect(self._call("DELETE", f"/users/{_quote(subject)}"), 200, 204)
        except HttpError as error:
            if error.status != 404:
                raise
            self._confirm_realm_answers()

    def list_user_session_ids(self, subject: str) -> tuple[str, ...]:
        """Ids of the user's active sessions. Used to check that a session belongs to the user."""
        return tuple(str(row.get("id", "")) for row in self._list(f"/users/{_quote(subject)}/sessions"))

    def delete_session(self, session_id: str) -> None:
        """End one Keycloak session. Its refresh token stops working too.

        Repeatable: a session that is already gone counts as done. A 404 alone does not
        prove that, because a wrong address answers 404 too, so the realm must answer.
        """
        try:
            _expect(self._call("DELETE", f"/sessions/{_quote(session_id)}"), 200, 204)
        except HttpError as error:
            if error.status != 404:
                raise
            self._confirm_realm_answers()

    # --- birleşik işler: tekrar edilebilir ---

    def ensure_organization_member(
        self, alias: str, name: str, subject: str, organization_id: str | None
    ) -> str:
        """Add the user to the planned organization. Returns the organization id.

        `organization_id` comes from the plan. None: create the organization, then add the
        member. Otherwise: add the member to exactly that organization.
        This function does not look the organization up. A new lookup could pick another
        target than the one a human approved. If the name was taken meanwhile, Keycloak
        rejects the create and the member is not added anywhere.
        """
        if organization_id is None:
            organization_id = str(self.create_organization(alias, name).value)
        self.add_organization_member(organization_id, subject)
        return organization_id

    def invite_user(
        self,
        email: str,
        first_name: str,
        last_name: str,
        organization_id: str,
        *,
        dry_run: bool = False,
        expected_previews: Sequence[Preview] | None = None,
        on_step: Callable[[str, str], None] | None = None,
        on_subject: Callable[[str], None] | None = None,
    ) -> InviteResult:
        """Invite a user (G-16, G-79).

        Creates the user if missing, adds the user to the organization and sends the invitation
        e-mail. With `dry_run` it only reads and returns the planned steps.
        `expected_previews` is the approved plan. If the current plan differs, `PlanChanged`
        is raised and nothing is written.

        `on_step(step, status)` is called with `writing` right before each write and with
        `done`, `failed` or `unknown` right after. The caller records it, so a stopped run
        shows which step may have happened. `on_subject` reports the new user's id.
        """
        existing = self.find_user_by_email(email)
        subject = str(existing["id"]) if existing else None
        shown = subject or "(new user)"
        plan: list[Preview] = []
        if subject is None:
            plan.append(self.create_user(email, first_name, last_name, dry_run=True).preview)
        plan.append(self.add_organization_member(organization_id, shown, dry_run=True).preview)
        plan.append(self.send_execute_actions_email(shown, INVITE_ACTIONS, dry_run=True).preview)
        if expected_previews is not None and tuple(plan) != tuple(expected_previews):
            raise PlanChanged
        if dry_run:
            return InviteResult(subject=subject, previews=tuple(plan))

        def step(name: str, write: Callable[[], Outcome]) -> Outcome:
            if on_step:
                on_step(name, "writing")
            try:
                outcome = write()
            except HttpError:
                if on_step:
                    on_step(name, "failed")
                raise
            except TransportError:
                if on_step:
                    on_step(name, "unknown")  # the request may have reached Keycloak
                raise
            if on_step:
                on_step(name, "done")
            return outcome

        if subject is None:
            subject = str(step("keycloak.create_user", lambda: self.create_user(email, first_name, last_name)).value)
        if on_subject:
            on_subject(subject)
        user_id = subject
        step("keycloak.add_organization_member", lambda: self.add_organization_member(organization_id, user_id))
        step("keycloak.send_execute_actions_email", lambda: self.send_execute_actions_email(user_id, INVITE_ACTIONS))
        return InviteResult(subject=subject, previews=tuple(plan))

def _organization(row: Mapping[str, object]) -> Organization:
    return Organization(id=str(row.get("id", "")), alias=str(row.get("alias", "")), name=str(row.get("name") or ""))


def snapshot_from_user(user: Mapping[str, object], organizations: Sequence[Organization]) -> UserSnapshot:
    return UserSnapshot(
        subject=str(user.get("id", "")),
        email=str(user.get("email") or ""),
        email_verified=user.get("emailVerified") is True,
        enabled=user.get("enabled") is True,
        first_name=str(user.get("firstName") or ""),
        last_name=str(user.get("lastName") or ""),
        organizations=tuple(organizations),
    )
