"""Clients for the identity endpoints of Press and tenant sites.

Endpoint names come from sections 5 and 6 of `docs/sozlesmeler.md`.
Each target receives a token containing only that target's `aud` value.

The `list_identities` endpoints and their paging are defined in the shared contract
(docs/sozlesmeler.md, section 7). A row carries only issuer, subject and the enabled state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict

from identity_sync.httpjson import ConnectFailed, HttpError, Response, TransportError, UnknownOutcome, request_json
from identity_sync.mapping import (
    PressAnonymizeUser,
    PressEnsureTeam,
    PressRemoveTeamMember,
    Tenant,
    TenantAnonymizeUser,
    TenantChangeEmail,
    TenantProvision,
    TenantRevokeUserInstallations,
    TenantSetEnabled,
)
from identity_sync.reconcile import Identity
from identity_sync.tokens import TokenProvider

PRESS_SCOPE = "aud-press"
_AMBIGUOUS_GATEWAY_STATUSES = (502, 504)


def tenant_scope(tenant: str) -> str:
    return f"aud-site-{tenant}"



Success = Callable[[object], bool]
IDENTITY_NOT_FOUND = "IdentityNotFound"


def _call_method(
    base_url: str,
    method_path: str,
    tokens: TokenProvider,
    scope: str,
    *,
    timeout: float,
    body: Mapping[str, object] | None = None,
    is_success: Success | None = None,
    missing_identity_is_success: bool = False,
    retry_statuses: tuple[int, ...] = (),
    query: Mapping[str, object] | None = None,
) -> object:
    """Call a Frappe method and return the `message` value of the reply.

    `retry_statuses`: statuses this endpoint uses for "try again", for example 409 for a
    lock conflict. The pipeline then retries a bounded number of times.

    A write (`body` given) counts as done only on HTTP 200 with a body that `is_success`
    accepts. The exact success bodies come from the target contracts. Being queued is not
    success: any other 2xx reply raises `UnknownOutcome`.

    `missing_identity_is_success`: the tenant answers 404 `IdentityNotFound` when it has no
    link for the user. For "disable" and "rename" that means there is nothing to do.
    A 404 without that error name is a failure: a wrong address answers 404 too.
    """

    def send(token: str) -> Response:
        try:
            return request_json(
                "GET" if body is None else "POST",
                f"{base_url.rstrip('/')}/api/method/{method_path}",
                timeout=timeout,
                headers={"Authorization": f"Bearer {token}"},
                query=query,
                json_body=body,
            )
        except ConnectFailed:
            raise  # the request was never sent: nothing is uncertain
        except TransportError:
            if body is None:
                raise
            # The write was sent but the reply could not be read. Nobody knows if it happened.
            raise UnknownOutcome from None
        except HttpError as error:
            # A gateway in between failed. The target may still have done the work.
            if body is not None and error.status in _AMBIGUOUS_GATEWAY_STATUSES:
                raise UnknownOutcome from None
            raise

    try:
        response = tokens.with_token(scope, send)
    except HttpError as error:
        if missing_identity_is_success and error.status == 404 and error.code == IDENTITY_NOT_FOUND:
            return None
        if error.status in retry_statuses:
            error.retryable = True
        raise
    message = response.body.get("message") if isinstance(response.body, Mapping) else None
    if body is not None and not (response.status == 200 and is_success is not None and is_success(message)):
        raise UnknownOutcome
    return message


def _text(message: object, name: str) -> str | None:
    value = message.get(name) if isinstance(message, Mapping) else None
    return value if isinstance(value, str) and value else None


def _is_team(message: object) -> bool:
    """ensure_team (press_tr contract): a team name and a `created` flag."""
    # `_text` returned a value, so `message` is a mapping here. The type checker cannot see that.
    return _text(message, "team") is not None and isinstance(message.get("created"), bool)  # type: ignore[union-attr]


# anonymize_user answers 409 on a lock conflict or timeout. The caller retries (docs/sozlesmeler.md, section 6).
ANONYMIZE_RETRY_STATUSES = (409,)


def _is_anonymized(message: object) -> bool:
    """anonymize_user (docs/sozlesmeler.md, section 6): the body carries `anonymized` and `found`.

    Done means the user is anonymized, or the target does not know the identity (`found` false).
    """
    if not isinstance(message, Mapping):
        return False
    anonymized, found = message.get("anonymized"), message.get("found")
    if not isinstance(anonymized, bool) or not isinstance(found, bool):
        return False
    return anonymized or not found


def _is_revoked(message: object) -> bool:
    """revoke_user_installations: `revoked` is the number of removed installations, 0 or more."""
    revoked = message.get("revoked") if isinstance(message, Mapping) else None
    return isinstance(revoked, int) and not isinstance(revoked, bool) and revoked >= 0


def _is_removed(message: object) -> bool:
    """remove_team_member (press_tr contract): `member` is false. `team` is a name or null."""
    return isinstance(message, Mapping) and message.get("member") is False and "team" in message


def _organization_ids(value: object) -> tuple[str, ...]:
    """Team memberships of a Press identity, one Keycloak organization id each. Tenants send none."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TransportError("identity row has invalid organization_ids")
    return tuple(value)


# `list_identities` paging (docs/sozlesmeler.md, section 7): `start` and `page_length`, at most 500.
IDENTITY_PAGE_LENGTH = 500
# A list longer than this is taken as a target that never ends its paging.
_MAX_IDENTITY_PAGES = 2000


def _all_identities(read_page: Callable[[Mapping[str, object]], object]) -> list[Identity]:
    """Read every page of a `list_identities` endpoint.

    The reply is `{"identities": [...], "has_next_page": bool}`, ordered by `subject`.
    The differences are computed only after the last page: an account on a later page must
    not look missing. A reply in another shape, or paging that never ends, is an error.
    Nothing is concluded from half a list.
    """
    found: dict[tuple[str, str], Identity] = {}
    for page in range(_MAX_IDENTITY_PAGES):
        message = read_page({"start": page * IDENTITY_PAGE_LENGTH, "page_length": IDENTITY_PAGE_LENGTH})
        if not isinstance(message, Mapping) or not isinstance(message.get("has_next_page"), bool):
            raise TransportError("identity list is not a page")
        before = len(found)
        for identity in _identities(message.get("identities")):
            found[(identity.issuer, identity.subject)] = identity
        if not message["has_next_page"]:
            return list(found.values())
        if len(found) == before:
            break  # the target says "more" but sends nothing new
    raise TransportError("identity list does not end")


def _identities(message: object) -> list[Identity]:
    if not isinstance(message, list):
        raise TransportError("identity list is not a list")
    rows = []
    for row in message:
        if not isinstance(row, Mapping):
            raise TransportError("identity row is not an object")
        rows.append(
            Identity(
                issuer=str(row.get("issuer", "")),
                subject=str(row.get("subject", "")),
                email=str(row.get("email") or ""),
                enabled=row.get("enabled") is True,
                # A row without the key says nothing about teams (docs/sozlesmeler.md, section 7).
                organization_ids=_organization_ids(row["organization_ids"]) if "organization_ids" in row else None,
            )
        )
    return rows


class PressClient:
    def __init__(
        self, base_url: str, tokens: TokenProvider, *, timeout: float, anonymize_timeout: float | None = None
    ) -> None:
        self._base_url = base_url
        self._tokens = tokens
        self._timeout = timeout
        self._anonymize_timeout = anonymize_timeout or timeout

    def _call(
        self,
        method_path: str,
        body: Mapping[str, object] | None = None,
        is_success: Success | None = None,
        retry_statuses: tuple[int, ...] = (),
        query: Mapping[str, object] | None = None,
        timeout: float | None = None,
    ) -> object:
        return _call_method(
            self._base_url,
            method_path,
            self._tokens,
            PRESS_SCOPE,
            timeout=timeout or self._timeout,
            body=body,
            is_success=is_success,
            retry_statuses=retry_statuses,
            query=query,
        )

    def anonymize_user(self, action: PressAnonymizeUser) -> None:
        """Close the Press user, revoke the API keys and anonymize the personal fields (docs/sozlesmeler.md, section 6).

        Press answers `found: false` for an identity it does not know. That counts as done.
        """
        body = {"issuer": action.issuer, "subject": action.subject}
        self._call(
            "press_tr.api.identity.anonymize_user",
            body,
            _is_anonymized,
            ANONYMIZE_RETRY_STATUSES,
            timeout=self._anonymize_timeout,
        )

    def ensure_team(self, action: PressEnsureTeam) -> None:
        body = asdict(action)
        if not action.organization_name:
            del body["organization_name"]  # optional field
        self._call("press_tr.api.identity.ensure_team", body, _is_team)

    def remove_team_member(self, action: PressRemoveTeamMember) -> None:
        """Remove the user from one organization's team, or from every team.

        The request carries exactly one of `organization_id` and `all_organizations: true`
        (docs/sozlesmeler.md, section 6). Press answers 400 to both, to neither, and to an
        empty `organization_id`.
        """
        body: dict[str, object] = {"issuer": action.issuer, "subject": action.subject}
        if action.organization_id is None:
            # Deleted or disabled user. Press also disables the user and revokes the API keys.
            body["all_organizations"] = True
        elif action.organization_id:
            body["organization_id"] = action.organization_id
        else:
            raise ValueError("organization_id must not be empty")
        self._call("press_tr.api.identity.remove_team_member", body, _is_removed)

    def list_identities(self) -> list[Identity]:
        return _all_identities(lambda page: self._call("press_tr.api.identity.list_identities", query=page))


class TenantClient:
    """Calls the tenant identity endpoints (contracts/platform_core-kimlik.openapi.yaml)."""

    def __init__(
        self, tenants: Sequence[Tenant], tokens: TokenProvider, *, timeout: float, anonymize_timeout: float | None = None
    ) -> None:
        self._tenants = {tenant.name: tenant for tenant in tenants}
        self._tokens = tokens
        self._timeout = timeout
        self._anonymize_timeout = anonymize_timeout or timeout

    def _call(
        self,
        tenant: str,
        method_path: str,
        body: Mapping[str, object] | None = None,
        is_success: Success | None = None,
        missing_identity_is_success: bool = False,
        retry_statuses: tuple[int, ...] = (),
        query: Mapping[str, object] | None = None,
        timeout: float | None = None,
    ) -> object:
        # The target address comes only from the configured tenant list (G-13).
        return _call_method(
            self._tenants[tenant].base_url,
            method_path,
            self._tokens,
            tenant_scope(tenant),
            timeout=timeout or self._timeout,
            body=body,
            is_success=is_success,
            missing_identity_is_success=missing_identity_is_success,
            retry_statuses=retry_statuses,
            query=query,
        )

    @staticmethod
    def _body(action: object) -> dict[str, object]:
        # Every action is a dataclass. The union type hides that from `asdict`.
        body = asdict(action)  # type: ignore[call-overload]
        del body["tenant"]
        return body

    def provision(self, action: TenantProvision) -> None:
        """Success: the linked user, with the requested `enabled` state."""

        def done(message: object) -> bool:
            return (
                _text(message, "user") is not None
                # `_text` returned a value, so `message` is a mapping here. The type checker cannot see that.
                and message.get("linked") is True  # type: ignore[union-attr]
                and message.get("enabled") is action.enabled  # type: ignore[union-attr]
            )

        self._call(action.tenant, "platform_core.api.identity.provision", self._body(action), done)

    def set_enabled(self, action: TenantSetEnabled) -> None:
        """Success: the user's final state equals the requested one.

        A tenant that has no link for the user has nothing to disable, so that counts as done.
        Enabling a user the tenant does not know stays a failure.
        """

        def done(message: object) -> bool:
            # `_text` returned a value, so `message` is a mapping here. The type checker cannot see that.
            return _text(message, "user") is not None and message.get("enabled") is action.enabled  # type: ignore[union-attr]

        self._call(
            action.tenant,
            "platform_core.api.identity.set_enabled",
            self._body(action),
            done,
            missing_identity_is_success=not action.enabled,
        )

    def change_email(self, action: TenantChangeEmail) -> None:
        """Success: the user's name is the new e-mail. No link yet means there is nothing to rename."""
        self._call(
            action.tenant,
            "platform_core.api.identity.change_email",
            self._body(action),
            lambda message: _text(message, "user") == action.new_email,
            missing_identity_is_success=True,
        )

    def revoke_user_installations(self, action: TenantRevokeUserInstallations) -> None:
        """Revoke every phone installation of the user (docs/sozlesmeler.md, section 5). No link: nothing to revoke."""
        self._call(
            action.tenant,
            "platform_core.api.mobile.revoke_user_installations",
            self._body(action),
            _is_revoked,
            missing_identity_is_success=True,
        )

    def anonymize_user(self, action: TenantAnonymizeUser) -> None:
        """Close the tenant user and anonymize the personal fields. No link: nothing to anonymize."""
        self._call(
            action.tenant,
            "platform_core.api.identity.anonymize_user",
            self._body(action),
            _is_anonymized,
            missing_identity_is_success=True,
            retry_statuses=ANONYMIZE_RETRY_STATUSES,
            timeout=self._anonymize_timeout,
        )

    def list_identities(self, tenant: str) -> list[Identity]:
        method = "platform_core.api.identity.list_identities"
        return _all_identities(lambda page: self._call(tenant, method, query=page))
