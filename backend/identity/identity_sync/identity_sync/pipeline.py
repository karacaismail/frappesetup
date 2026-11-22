"""The event pipeline.

Order of work: read the user's current state, plan the actions, run the actions.
A failed event goes to the dead-letter queue. The queue is replayed only by hand.
This module has no scheduled job and no polling loop (Proje kaydı D-6).

All work on an event runs under the work lock, so the server and the
`replay-dead-letters` command cannot run the same event together, and two events of
one user are serialized. Every record is durable at once.

An approved replay holds the lock for the whole request: it plans every event, checks
the digest, and then writes exactly those plans. If any plan differs from the approved
one, nothing is written.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from typing import TypeVar

from identity_sync.events import DELETION_TYPES, MEMBERSHIP_TYPES, Event, is_handled
from identity_sync.httpjson import HttpError, TransportError, UnknownOutcome
from identity_sync.keycloak_admin import KeycloakAdmin
from identity_sync.mapping import (
    Action,
    EnsureOrganization,
    KeycloakDeleteUser,
    KeycloakDisableUser,
    PressAnonymizeUser,
    PressEnsureTeam,
    PressRemoveTeamMember,
    Preview,
    Tenant,
    TenantAnonymizeUser,
    TenantChangeEmail,
    TenantProvision,
    TenantRevokeUserInstallations,
    TenantSetEnabled,
    digest_of,
    plan_actions,
)
from identity_sync.sites import PressClient, TenantClient
from identity_sync.store import Store

T = TypeVar("T")

# After an organization was created, the state is read once more and the plan is renewed.
_MAX_PASSES = 2
_BACKOFF_SECONDS = 0.2


@dataclass(frozen=True)
class EventResult:
    """`status` values are in the `EventResult` schema of the contract."""

    status: str
    actions: tuple[str, ...] = ()
    previews: tuple[Preview, ...] = ()
    plan_digest: str = ""

    def to_dict(self) -> dict[str, object]:
        body: dict[str, object] = {"status": self.status, "actions": list(self.actions)}
        if self.status == "preview":
            body["previews"] = [preview.to_dict() for preview in self.previews]
            body["plan_digest"] = self.plan_digest
        return body


def plan_digest(actions: Sequence[Action], key: bytes) -> str:
    """Keyed digest of everything a plan would write: each operation, its target and every field value.

    The preview text names no e-mail or person name, so two plans can read the same and still
    write different values. The digest covers those values, and the real organization id of an
    organization step. It is an HMAC, so it exposes none of them.
    """
    return digest_of(
        [
            {"operation": action.preview().operation, "target": action.preview().target, "fields": asdict(action)}
            for action in actions
        ],
        key,
    )


ReplayResults = list[tuple[str, EventResult]]


def replay_report(results: ReplayResults) -> list[dict[str, object]]:
    return [{"event_id": event_id, **result.to_dict()} for event_id, result in results]


class PreviewChanged(Exception):
    """The plan is not the approved one. The approval belongs to the old plan. Nothing is written."""


class _Failed(Exception):
    """A step failed for good. The text carries no personal data."""

    def __init__(self, message: str, *, unknown: bool = False) -> None:
        super().__init__(message)
        self.unknown = unknown


class Processor:
    def __init__(
        self,
        *,
        issuer: str,
        realm: str,
        tenants: Sequence[Tenant],
        keycloak: KeycloakAdmin,
        press: PressClient,
        tenant_client: TenantClient,
        store: Store,
        digest_key: bytes,
        max_attempts: int = 3,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        self._issuer = issuer
        self._realm = realm
        self._tenants = tuple(tenants)
        self._keycloak = keycloak
        self._press = press
        self._tenant_client = tenant_client
        self._store = store
        self._digest_key = digest_key
        self._max_attempts = max_attempts
        self._sleep = sleep

    def handle(
        self,
        event: Event,
        *,
        dry_run: bool = False,
        allow_unknown: bool = False,
        approved_digest: str | None = None,
    ) -> EventResult:
        """Process one event.

        `dry_run`: only read and return the preview.
        `allow_unknown`: permission to run an event whose earlier outcome is unknown.
        That is a human's explicit decision.
        `approved_digest`: the `plan_digest` a human approved. The plan is built under the work
        lock. If it differs, `PreviewChanged` is raised and nothing is written. Otherwise exactly
        that plan is written.
        """
        if not is_handled(event) or event.realm != self._realm:
            return EventResult("ignored")
        if dry_run:
            return self._preview(event)[0]
        # The duplicate check, the external writes and the record are under one work lock.
        with self._store.work_lock():
            planned = None
            if approved_digest is not None:
                preview, planned = self._preview(event)
                if planned is None or preview.plan_digest != approved_digest:
                    raise PreviewChanged
            return self._handle_locked(event, allow_unknown, planned)

    def _preview(self, event: Event) -> tuple[EventResult, tuple[Action, ...] | None]:
        """Plan the event and describe the plan. Reads only. The second value is None when planning failed."""
        try:
            actions = self._plan(event)
        except _Failed:
            return EventResult("failed"), None
        result = EventResult(
            "preview",
            previews=tuple(action.preview() for action in actions),
            plan_digest=plan_digest(actions, self._digest_key),
        )
        return result, actions

    def _handle_locked(self, event: Event, allow_unknown: bool, planned: tuple[Action, ...] | None) -> EventResult:
        """Run one event. The caller holds the work lock.

        `planned` is a plan that was already checked against an approval. It is written as it is.
        """
        if self._store.is_processed(event.id):
            # A row left in the queue is a leftover. It would make every replay look failed.
            self._store.remove_dead_letter(event.id)
            return EventResult("duplicate")
        if not allow_unknown and self._store.dead_letter_state(event.id) == "unknown":
            # The event came again but its earlier outcome is unknown. No blind repeat.
            return EventResult("unknown")
        # Keep the accepted event on record before any work. A crash must not lose it.
        self._store.begin(event)
        try:
            names = self._run(event, planned)
        except _Failed as failure:
            # An event with an unknown outcome is not counted as processed (docs/sozlesmeler.md, section 10).
            state = "unknown" if failure.unknown else "failed"
            self._store.add_dead_letter(event, str(failure), state=state)
            return EventResult("unknown" if failure.unknown else "dead_lettered")
        self._store.mark_processed(event.id, "processed")
        return EventResult("processed", actions=tuple(names))

    def replay_dead_letters(
        self, *, dry_run: bool = False, include_unknown: bool = False, expected_digest: str | None = None
    ) -> ReplayResults:
        """Process the events in the dead-letter queue once. Started by hand.

        Events with an unknown outcome are skipped: no blind repeat on the same target.
        `include_unknown` processes them too. That is a human's explicit decision.

        `expected_digest` is the digest of the approved preview. The whole request then runs
        under the work lock: every event is planned, the digest is checked, and exactly those
        plans are written. If the plan of any event differs, `PreviewChanged` is raised and
        no event is written. An event whose preview could not be built is not run.
        """
        if dry_run:
            return self._ordered(self._replay_previews(include_unknown)[0])
        if expected_digest is None:
            letters, skipped = self._letters(include_unknown)
            results = [(letter.event.id, self.handle(letter.event, allow_unknown=include_unknown)) for letter in letters]
            return self._ordered(results + skipped)
        with self._store.work_lock():
            previews, plans = self._replay_previews(include_unknown)
            if digest_of(replay_report(self._ordered(previews)), self._digest_key) != expected_digest:
                raise PreviewChanged
            letters, skipped = self._letters(include_unknown)
            results: ReplayResults = []
            for letter in letters:
                plan = plans.get(letter.event.id)
                if plan is None:
                    results.append((letter.event.id, EventResult("failed")))  # no plan was seen: do not run
                else:
                    results.append((letter.event.id, self._handle_locked(letter.event, include_unknown, plan)))
            return self._ordered(results + skipped)

    def _letters(self, include_unknown: bool) -> tuple[list, ReplayResults]:
        """Split the queue into events to run and events to skip."""
        letters, skipped = [], []
        for letter in self._store.dead_letters():
            if letter.state == "unknown" and not include_unknown:
                skipped.append((letter.event.id, EventResult("unknown")))
            else:
                letters.append(letter)
        return letters, skipped

    def _replay_previews(self, include_unknown: bool) -> tuple[ReplayResults, dict[str, tuple[Action, ...]]]:
        letters, skipped = self._letters(include_unknown)
        previews: ReplayResults = []
        plans: dict[str, tuple[Action, ...]] = {}
        for letter in letters:
            result, actions = self._preview(letter.event)
            previews.append((letter.event.id, result))
            if actions is not None:
                plans[letter.event.id] = actions
        return previews + skipped, plans

    def _ordered(self, results: ReplayResults) -> ReplayResults:
        """Put the results in queue order. The digest depends on this order."""
        order = {letter.event.id: index for index, letter in enumerate(self._store.dead_letters())}
        return sorted(results, key=lambda item: order.get(item[0], len(order)))

    def run_actions(self, actions: Sequence[Action]) -> list[dict[str, str]]:
        """Run a list of actions and report each outcome. Used by the reconcile repair.

        Every action is attempted. `status` is `done`, `failed` or `unknown`.
        An unknown outcome is not retried. The caller holds the work lock.
        """
        results: list[dict[str, str]] = []
        for action in actions:
            preview = action.preview()
            result = {"operation": preview.operation, "target": preview.target, "status": "done"}
            try:
                self._retry(f"{preview.operation} {preview.target}", lambda action=action: self._execute(action))
            except _Failed as failure:
                result.update(status="failed", error=str(failure))
            except UnknownOutcome:
                result.update(status="unknown", error=f"{preview.operation} {preview.target}: unknown outcome")
            results.append(result)
        return results

    def _plan(self, event: Event) -> tuple[Action, ...]:
        subject = event.user_id or ""
        if event.type in DELETION_TYPES:
            # The deletion flow is the same whatever the user's state is. It needs no read.
            return plan_actions(event, None, issuer=self._issuer, tenants=self._tenants)
        snapshot = self._retry("keycloak.read", lambda: self._keycloak.get_user_snapshot(subject))
        organization = None
        # A deleted or disabled account is closed everywhere. That plan does not use the
        # organization, so a failing organization read must not stop it.
        needs_organization = snapshot is not None and snapshot.enabled
        if needs_organization and event.type in MEMBERSHIP_TYPES and event.organization_id:
            org_id = event.organization_id
            organization = self._retry("keycloak.read", lambda: self._keycloak.get_organization(org_id))
        actions = plan_actions(
            event, snapshot, issuer=self._issuer, tenants=self._tenants, organization=organization
        )
        return tuple(self._resolve(action) for action in actions)

    def _resolve(self, action: Action) -> Action:
        """Put the real organization id into an organization step.

        The lookup happens here, at plan time. The preview and the digest then name the real
        target, and the execution writes to exactly that target.
        """
        if not isinstance(action, EnsureOrganization):
            return action
        found = self._retry("keycloak.read", lambda: self._keycloak.find_organization(action.name, action.alias))
        return replace(action, organization_id=found.id if found else None)

    def _run(self, event: Event, planned: tuple[Action, ...] | None) -> list[str]:
        names: list[str] = []
        for pass_number in range(1, _MAX_PASSES + 1):
            if pass_number == 1 and planned is not None:
                actions = planned  # already checked against the approval: no second read
            else:
                actions = self._plan(event)
            if pass_number > 1:
                if planned is not None:
                    # The follow-up actions were not in the preview. The human did not see them.
                    raise _Failed("follow-up actions need a new preview")
                if any(isinstance(action, EnsureOrganization) for action in actions):
                    # The organization was created but the membership is still not visible.
                    # The team and tenant work did not run.
                    raise _Failed("keycloak.ensure_organization: membership not visible yet")
            if actions and pass_number == 1:
                # From the first external write on, a crash leaves the outcome unknown.
                self._store.mark_writing(event.id)
            failures: list[str] = []
            unknown = False
            for action in actions:
                preview = action.preview()
                label = f"{preview.operation} {preview.target}"
                if isinstance(action, KeycloakDeleteUser) and failures:
                    # Deleting the Keycloak user is the last, irreversible step. It waits until
                    # every earlier step is done. The request stays in the queue for a replay.
                    failures.append(f"{label}: skipped because an earlier step is not done")
                    continue
                # A failed step does not stop the others. For example the user is still disabled
                # on every tenant when Press does not answer. The steps are repeatable.
                try:
                    self._retry(label, lambda action=action: self._execute(action))
                except _Failed as failure:
                    failures.append(str(failure))
                except UnknownOutcome:
                    # Unknown outcome. No blind repeat.
                    failures.append(f"{label}: unknown outcome")
                    unknown = True
                else:
                    names.append(preview.operation)
            if failures:
                raise _Failed("; ".join(failures), unknown=unknown)
            if not any(isinstance(action, EnsureOrganization) for action in actions):
                return names
        raise _Failed("keycloak.ensure_organization: membership not visible yet")

    def _execute(self, action: Action) -> None:
        if isinstance(action, EnsureOrganization):
            self._keycloak.ensure_organization_member(action.alias, action.name, action.subject, action.organization_id)
        elif isinstance(action, PressEnsureTeam):
            self._press.ensure_team(action)
        elif isinstance(action, PressRemoveTeamMember):
            self._press.remove_team_member(action)
        elif isinstance(action, TenantProvision):
            self._tenant_client.provision(action)
        elif isinstance(action, TenantSetEnabled):
            self._tenant_client.set_enabled(action)
        elif isinstance(action, TenantChangeEmail):
            self._tenant_client.change_email(action)
        elif isinstance(action, TenantRevokeUserInstallations):
            self._tenant_client.revoke_user_installations(action)
        elif isinstance(action, TenantAnonymizeUser):
            self._tenant_client.anonymize_user(action)
        elif isinstance(action, PressAnonymizeUser):
            self._press.anonymize_user(action)
        elif isinstance(action, KeycloakDisableUser):
            self._keycloak.disable_user(action.subject)
        elif isinstance(action, KeycloakDeleteUser):
            self._keycloak.delete_user(action.subject)
        else:  # pragma: no cover - a new action type shows up here
            raise TypeError(f"unknown action: {type(action).__name__}")

    def _retry(self, label: str, call: Callable[[], T]) -> T:
        """Retry a bounded number of times on a transient error. Give up at once on a permanent one.

        `UnknownOutcome` is not retried and passes to the caller.
        """
        for attempt in range(1, self._max_attempts + 1):
            try:
                return call()
            except HttpError as error:
                reason, transient = str(error), error.transient
            except TransportError as error:
                # These texts are fixed. They carry no response body.
                reason, transient = str(error) or "network error", True
            if not transient or attempt == self._max_attempts:
                raise _Failed(f"{label}: {reason}")
            self._sleep(_BACKOFF_SECONDS * 2 ** (attempt - 1))
        raise _Failed(f"{label}: no attempt made")
