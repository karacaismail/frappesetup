"""Press ve kiracı sitelerinin kimlik uçlarını çağıran istemciler.

Uç adlarının kaynağı `docs/sozlesmeler.md` dosyasının 5. ve 6. bölümüdür.
Her hedefe yalnız o hedefin `aud` değerini taşıyan belirteç gider.

`list_identities` uçları ortak sözleşmede henüz yoktur. Mutabakat bu uçları ister.
BORC(mvp): Uçlar sözleşmeye girince adları buradan doğrulanır. Sorumlu: identity-sync işi.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict

from identity_sync.httpjson import TransportError, request_json
from identity_sync.mapping import (
    PressEnsureTeam,
    PressRemoveTeamMember,
    Tenant,
    TenantChangeEmail,
    TenantProvision,
    TenantSetEnabled,
)
from identity_sync.reconcile import Identity
from identity_sync.tokens import TokenProvider

PRESS_SCOPE = "aud-press"


def tenant_scope(tenant: str) -> str:
    return f"aud-site-{tenant}"


def _call_method(
    base_url: str,
    method_path: str,
    tokens: TokenProvider,
    scope: str,
    *,
    timeout: float,
    body: Mapping[str, object] | None = None,
) -> object:
    """Frappe ucunu çağırır ve yanıttaki `message` değerini döner."""
    response = tokens.with_token(
        scope,
        lambda token: request_json(
            "GET" if body is None else "POST",
            f"{base_url.rstrip('/')}/api/method/{method_path}",
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            json_body=body,
        ),
    )
    return response.body.get("message") if isinstance(response.body, Mapping) else None


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
            )
        )
    return rows


class PressClient:
    def __init__(self, base_url: str, tokens: TokenProvider, *, timeout: float) -> None:
        self._base_url = base_url
        self._tokens = tokens
        self._timeout = timeout

    def _call(self, method_path: str, body: Mapping[str, object] | None = None) -> object:
        return _call_method(self._base_url, method_path, self._tokens, PRESS_SCOPE, timeout=self._timeout, body=body)

    def ensure_team(self, action: PressEnsureTeam) -> None:
        self._call("press_tr.api.identity.ensure_team", asdict(action))

    def remove_team_member(self, action: PressRemoveTeamMember) -> None:
        self._call("press_tr.api.identity.remove_team_member", asdict(action))

    def list_identities(self) -> list[Identity]:
        return _identities(self._call("press_tr.api.identity.list_identities"))


class TenantClient:
    def __init__(self, tenants: Sequence[Tenant], tokens: TokenProvider, *, timeout: float) -> None:
        self._tenants = {tenant.name: tenant for tenant in tenants}
        self._tokens = tokens
        self._timeout = timeout

    def _call(self, tenant: str, method_path: str, body: Mapping[str, object] | None = None) -> object:
        # Hedef adres yalnız ayardaki kiracı listesinden gelir (G-13).
        base_url = self._tenants[tenant].base_url
        return _call_method(base_url, method_path, self._tokens, tenant_scope(tenant), timeout=self._timeout, body=body)

    @staticmethod
    def _body(action: object) -> dict[str, object]:
        body = asdict(action)  # type: ignore[call-overload]
        del body["tenant"]
        return body

    def provision(self, action: TenantProvision) -> None:
        self._call(action.tenant, "platform_core.api.identity.provision", self._body(action))

    def set_enabled(self, action: TenantSetEnabled) -> None:
        self._call(action.tenant, "platform_core.api.identity.set_enabled", self._body(action))

    def change_email(self, action: TenantChangeEmail) -> None:
        self._call(action.tenant, "platform_core.api.identity.change_email", self._body(action))

    def list_identities(self, tenant: str) -> list[Identity]:
        return _identities(self._call(tenant, "platform_core.api.identity.list_identities"))
