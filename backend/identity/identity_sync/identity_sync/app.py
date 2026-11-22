"""Wire the service components together."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from identity_sync.config import Settings
from identity_sync.keycloak_admin import KeycloakAdmin, snapshot_from_user
from identity_sync.mapping import Action, Organization, digest_of
from identity_sync.pipeline import PreviewChanged, Processor, plan_digest
from identity_sync.mapping import Preview
from identity_sync.reconcile import DELETED, Difference, deleted_subjects, find_differences, plan_repairs
from identity_sync.sites import PressClient, TenantClient
from identity_sync.store import Store
from identity_sync.tokens import TokenProvider


@dataclass(frozen=True)
class ReconcilePlan:
    """What reconcile found and what it would do about it. Building a plan only reads."""

    differences: tuple[Difference, ...]
    actions: tuple[Action, ...]
    # Keyed digest of the differences and of everything the repair would write.
    digest: str
    # Accounts deleted in Keycloak. Each is finished by its ordered account job.
    deleted: tuple[str, ...] = ()
    job_previews: tuple[Preview, ...] = ()
    # The differences as a reply shows them. A deleted account is named by its job id.
    shown: tuple[dict[str, str], ...] = ()

    def previews(self) -> list[Preview]:
        return [action.preview() for action in self.actions] + list(self.job_previews)

    def report(self) -> dict[str, object]:
        """The report for a human. It carries no e-mail: users are named by `sub`."""
        return {
            "count": len(self.differences),
            "differences": list(self.shown),
            "previews": [preview.to_dict() for preview in self.previews()],
            "preview_digest": self.digest,
        }


@dataclass
class App:
    settings: Settings
    store: Store
    keycloak: KeycloakAdmin
    press: PressClient
    tenant_client: TenantClient
    processor: Processor

    @property
    def digest_key(self) -> bytes:
        return self.settings.digest_key.encode("utf-8")

    def digest(self, value: object) -> str:
        """Keyed digest of a preview. See `mapping.digest_of`."""
        return digest_of(value, self.digest_key)

    def reconcile_plan(self) -> ReconcilePlan:
        """Compare Keycloak with Press and the tenants. Reads only. Started by hand, never scheduled."""
        memberships: dict[str, list[Organization]] = {}
        for organization in self.keycloak.list_organizations():
            for member in self.keycloak.list_organization_members(organization.id):
                memberships.setdefault(str(member.get("id", "")), []).append(organization)
        users = [
            snapshot_from_user(user, memberships.get(str(user.get("id", "")), ()))
            for user in self.keycloak.list_users()
        ]
        tenants = self.settings.tenants
        tenant_records = {tenant.name: self.tenant_client.list_identities(tenant.name) for tenant in tenants}
        differences = find_differences(
            users, self.press.list_identities(), tenant_records, issuer=self.settings.issuer, tenants=tenants
        )
        actions = plan_repairs(differences, users, issuer=self.settings.issuer, tenants=tenants)
        deleted = deleted_subjects(differences)
        # The remaining steps of each account job. A step an earlier run finished is not shown.
        jobs = [self.processor.removal_preview(subject) for subject in deleted]
        digest = self.digest(
            {
                "differences": [difference.to_dict() for difference in differences],
                "plan": plan_digest(actions, self.digest_key),
                "jobs": [job.plan_digest for job in jobs],
            }
        )
        job_previews = tuple(preview for job in jobs for preview in job.previews)
        shown = tuple(self._shown(difference) for difference in differences)
        return ReconcilePlan(tuple(differences), actions, digest, deleted, job_previews, shown)

    def _shown(self, difference: Difference) -> dict[str, str]:
        """A difference as a reply shows it.

        An account deleted in Keycloak is named by the id of its deletion job, a keyed digest.
        Its raw id does not leave the service. Every other kind names the user by `sub`,
        because the reader needs the id to act on a living account.
        """
        shown = difference.to_dict()
        if difference.kind == DELETED:
            shown["job_id"] = self.processor.account_job(shown.pop("subject"), time=0).id
        return shown

    def reconcile_execute(self, expected_digest: str) -> dict[str, object]:
        """Run the approved repair.

        The plan is built again under the work lock. If it is not exactly the approved one,
        `PreviewChanged` is raised and nothing is written. Otherwise that same plan runs.
        """
        with self.store.work_lock():
            plan = self.reconcile_plan()
            if plan.digest != expected_digest:
                raise PreviewChanged
            results = self.processor.run_actions(plan.actions)
            # Each deleted account: the remaining deletion steps, in order.
            results += [self.processor.run_removal(subject) for subject in plan.deleted]
        return {
            "count": len(plan.differences),
            "differences": list(plan.shown),
            "results": results,
        }

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
    press = PressClient(
        settings.press_url, tokens, timeout=settings.http_timeout, anonymize_timeout=settings.anonymize_timeout
    )
    tenant_client = TenantClient(
        settings.tenants, tokens, timeout=settings.http_timeout, anonymize_timeout=settings.anonymize_timeout
    )
    processor = Processor(
        issuer=settings.issuer,
        realm=settings.realm,
        tenants=settings.tenants,
        keycloak=keycloak,
        press=press,
        tenant_client=tenant_client,
        store=store,
        digest_key=settings.digest_key.encode("utf-8"),
        sleep=sleep,
        # A repeat inside a deletion request waits at most the anonymize timeout. 30 seconds cover
        # the retry pauses. A crashed process cannot keep the claim longer.
        repeat_hold=settings.anonymize_timeout + 30.0,
    )
    return App(settings, store, keycloak, press, tenant_client, processor)
