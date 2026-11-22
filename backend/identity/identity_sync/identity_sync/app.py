"""Servisin parçalarını birbirine bağlar."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from identity_sync.config import Settings
from identity_sync.keycloak_admin import KeycloakAdmin, snapshot_from_user
from identity_sync.mapping import Organization
from identity_sync.pipeline import Processor
from identity_sync.reconcile import Difference, compare, expected_identities
from identity_sync.sites import PressClient, TenantClient
from identity_sync.store import Store
from identity_sync.tokens import TokenProvider


@dataclass
class App:
    settings: Settings
    store: Store
    keycloak: KeycloakAdmin
    press: PressClient
    tenant_client: TenantClient
    processor: Processor

    def reconcile(self) -> list[Difference]:
        """Keycloak, Press ve kiracı kullanıcılarını karşılaştırır. Yalnız okur."""
        users: dict[str, dict[str, object]] = {}
        memberships: dict[str, list[Organization]] = {}
        for organization in self.keycloak.list_organizations():
            for member in self.keycloak.list_organization_members(organization.id):
                subject = str(member.get("id", ""))
                users[subject] = dict(member)
                memberships.setdefault(subject, []).append(organization)
        snapshots = [snapshot_from_user(user, memberships[subject]) for subject, user in users.items()]
        press_expected, tenant_expected = expected_identities(
            snapshots, issuer=self.settings.issuer, tenants=self.settings.tenants
        )
        differences = compare(press_expected, self.press.list_identities(), target="press")
        for tenant in self.settings.tenants:
            actual = self.tenant_client.list_identities(tenant.name)
            differences += compare(tenant_expected[tenant.name], actual, target=tenant.name)
        return differences

    def close(self) -> None:
        self.store.close()


def build_app(settings: Settings, *, sleep: Callable[[float], object] = time.sleep) -> App:
    tokens = TokenProvider(
        settings.token_url, settings.client_id, settings.client_secret, timeout=settings.http_timeout
    )
    store = Store(settings.db_path, lock_timeout=settings.lock_timeout)
    keycloak = KeycloakAdmin(
        settings.keycloak_base_url,
        settings.realm,
        tokens,
        admin_scope=settings.admin_scope,
        timeout=settings.http_timeout,
    )
    press = PressClient(settings.press_url, tokens, timeout=settings.http_timeout)
    tenant_client = TenantClient(settings.tenants, tokens, timeout=settings.http_timeout)
    processor = Processor(
        issuer=settings.issuer,
        realm=settings.realm,
        tenants=settings.tenants,
        keycloak=keycloak,
        press=press,
        tenant_client=tenant_client,
        store=store,
        sleep=sleep,
    )
    return App(settings, store, keycloak, press, tenant_client, processor)
