"""The event pipeline.

Order of work: read the user's current state, plan the actions, run the actions.
A failed event goes to the dead-letter queue. The queue is replayed only by hand.
This module has no scheduled job and no polling loop (project record D-6).

All work on an event runs under the work lock, so the server and the
`replay-dead-letters` command cannot run the same event together, and two events of
one user are serialized. Every record is durable at once.

An approved replay holds the lock for the whole request: it plans every event, checks
the digest, and then writes exactly those plans. If any plan differs from the approved
one, nothing is written.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from typing import NamedTuple, TypeVar

from identity_sync.events import (
    ACCOUNT_DELETION,
    ACCOUNT_REMOVAL,
    JOB_TYPES,
    MEMBERSHIP_TYPES,
    REQUEST_KIND,
    USER_REMOVED_TYPES,
    Event,
    is_handled,
)
from identity_sync.deadline import deadline, remaining
from identity_sync.httpjson import HttpError, TransportError, UnknownOutcome
from identity_sync.keycloak_admin import KeycloakAdmin
from identity_sync.mapping import (
    Action,
    EnsureOrganization,
    KeycloakDeleteUser,
    KeycloakDisableUser,
    OrderedPlan,
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
from identity_sync.store import Busy, DeadLetter, Store

T = TypeVar("T")

# After an organization was created, the state is read once more and the plan is renewed.
_MAX_PASSES = 2
_BACKOFF_SECONDS = 0.2
# Repeats of a queued account deletion job (H-5). Every step of the job may be repeated.
# One handled event settles at most this many jobs and spends at most this long on them.
SETTLE_MAX_JOBS = 3
SETTLE_BUDGET_SECONDS = 5.0
# An event repeats one job at most this often, and waits this long between two repeats.
SETTLE_MAX_ATTEMPTS = 5
SETTLE_INTERVAL_SECONDS = 30.0
# A claim stays this much longer than the anonymize timeout. After a client timeout the target
# may still work on the first call. Until the claim ends, no second call is sent (inceleme 18).
REPEAT_HOLD_MARGIN_SECONDS = 30.0
# Recording outcomes may take this long after the deadline, all records together (inceleme 19).
RECORD_GRACE_SECONDS = 5.0


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


class _Planned(NamedTuple):
    """A plan together with the record it belongs to.

    `record` is the event itself, or the account job a delete event was turned into. A plan
    that was checked against an approval is written under exactly this record. The execution
    never asks Keycloak again which record it is: the answer could differ from the one the
    human saw, and the approved steps would be booked under the wrong record.
    """

    record: Event
    actions: tuple[Action, ...]


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
        anonymize_timeout: float = 30.0,
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
        # The longest wait for one anonymize call. A claim lasts this long plus a margin.
        self._anonymize_timeout = anonymize_timeout

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

    def account_job(self, subject: str, *, time: int, removed: bool = False) -> Event:
        """The one deletion job of an account (docs/sozlesmeler.md, section 7).

        The Press request, the Keycloak delete event and the reconcile repair all become this
        job. Its id is a keyed digest of the account, so they share one record and one list of
        finished steps, and the record does not show whose account it is.
        `removed`: Keycloak no longer has the user, so only steps 2, 3 and 4 are planned.
        """
        key = {"operation": "delete_account", "issuer": self._issuer, "subject": subject}
        return Event(
            id="del-" + digest_of(key, self._digest_key)[:40],
            kind=REQUEST_KIND,
            type=ACCOUNT_REMOVAL if removed else ACCOUNT_DELETION,
            realm=self._realm,
            time=time,
            user_id=subject,
        )

    def _as_job(self, event: Event) -> Event:
        """Turn a Keycloak delete event into the account job, once Keycloak confirms the user is gone.

        This read is the only place that decides a deletion. If it fails, `_Failed` is raised:
        the caller keeps the event in the queue and writes nothing. No later read may plan the
        deletion under the event's own id, because the finished steps are recorded under the job.
        """
        subject = event.user_id
        if event.kind == REQUEST_KIND or event.type not in USER_REMOVED_TYPES or not subject:
            return event
        user = self._retry("keycloak.read", lambda: self._keycloak.get_user(subject))
        if user is not None:
            return event  # Keycloak still has the user: the current state decides, nothing is anonymized
        return self.account_job(subject, time=event.time, removed=True)

    def _job_id(self, subject: str) -> str:
        return self.account_job(subject, time=0).id

    def _account_deleted(self, subject: str) -> bool:
        """Is the deletion job of this account finished? The finished record is the keyed digest."""
        return self._store.is_processed(self._job_id(subject))

    def hides_account(self, event: Event) -> bool:
        """Must a reply about this event leave out the account id?

        Yes for the account job, for a Keycloak delete event, and for any event of an account
        whose deletion job exists, waiting or finished.
        """
        subject = event.user_id
        if not subject:
            return False
        if event.kind == REQUEST_KIND or event.type in USER_REMOVED_TYPES:
            return True
        job_id = self._job_id(subject)
        return self._store.dead_letter_state(job_id) is not None or self._store.is_processed(job_id)

    def listed(self, letter: DeadLetter) -> dict[str, object]:
        """A queue record as a reply shows it."""
        record = letter.to_dict()
        if self.hides_account(letter.event):
            record["event"].pop("user_id", None)
        return record

    def _step_key(self, action: Action) -> str:
        return plan_digest((action,), self._digest_key)

    def _pending(self, event: Event, actions: tuple[Action, ...]) -> tuple[Action, ...]:
        """The steps still to run. An ordered plan skips the steps an earlier run finished."""
        if not isinstance(actions, OrderedPlan):
            return actions
        finished = self._store.progress(event.id)
        return tuple(action for action in actions if self._step_key(action) not in finished)

    def _describe(self, event: Event, action: Action) -> Preview:
        """The preview of one step.

        A step of an account deletion never names the account. It names the deletion job, whose
        id is a keyed digest. This holds for the account job and for a Keycloak delete event,
        whatever Keycloak answered: gone, closed or open. Only the text changes. The plan stays
        with its own record and the digest is computed from the real steps.
        """
        preview = action.preview()
        subject = event.user_id
        if not subject or not self.hides_account(event):
            return preview
        job_id = self._job_id(subject)
        summary = preview.summary.replace(f"user {subject}", f"the user of deletion job {job_id}")
        return replace(preview, summary=summary.replace(subject, job_id))

    def _preview(self, event: Event) -> tuple[EventResult, _Planned | None]:
        """Plan the event and describe the plan. Reads only. The second value is None when planning failed.

        The digest covers the record the plan belongs to, not only its steps. If Keycloak answers
        differently at execution time, the record or the steps differ and the digest does not match.
        """
        try:
            event = self._as_job(event)
            actions = self._plan(event)
        except _Failed:
            return EventResult("failed"), None
        # An ordered plan may be partly done. The preview shows what is still to do.
        pending = self._pending(event, actions)
        result = EventResult(
            "preview",
            previews=tuple(self._describe(event, action) for action in pending),
            plan_digest=digest_of({"record": event.id, "steps": plan_digest(pending, self._digest_key)}, self._digest_key),
        )
        return result, _Planned(event, actions)

    def removal_preview(self, subject: str) -> EventResult:
        """Preview the job for an account that Keycloak no longer has. Used by reconcile. Reads only."""
        return self._preview(self.account_job(subject, time=0, removed=True))[0]

    def run_removal(self, subject: str) -> dict[str, str]:
        """Run the job for an account that Keycloak no longer has. The caller holds the work lock.

        The steps run in order and stop at the first one that is not done. Steps that an
        earlier run finished are not called again.
        """
        job = self.account_job(subject, time=int(time.time() * 1000), removed=True)
        result = {"operation": "account_deletion", "target": job.id}
        if self._store.is_processed(job.id):
            # The job finished before, yet a target still lists the account. A human must look.
            return {**result, "status": "failed", "error": "the deletion job finished before; check the target"}
        # A human approved this repair. Like a human replay, it skips the count and spacing limits.
        status = self._handle_job(job, True, None).status
        if status == "processed":
            return {**result, "status": "done"}
        if status == "unknown":
            return {**result, "status": "unknown", "error": "a step has an unknown outcome; see the dead-letter queue"}
        return {**result, "status": "failed", "error": "a step failed; see the dead-letter queue"}

    def _handle_locked(self, event: Event, allow_unknown: bool, planned: _Planned | None) -> EventResult:
        """Run one event. The caller holds the work lock.

        `planned` is a plan that was already checked against an approval. It is written as it
        is, under the record it was planned for. Keycloak is not asked again.
        """
        if event.kind != REQUEST_KIND and event.user_id and self._account_deleted(event.user_id):
            # The account of this event is deleted. The service knows that only by the keyed
            # digest of the finished job. The event is not run, and it is not recorded: a record
            # would write the raw id of the deleted account back into the store.
            self._store.remove_dead_letter(event.id)
            return EventResult("duplicate")
        if planned is not None:
            result = self._handle_job(planned.record, allow_unknown, planned.actions)
            if planned.record.id != event.id:
                self._store.remove_dead_letter(event.id)
            return result
        try:
            job = self._as_job(event)
        except _Failed as failure:
            # Keycloak could not say whether the user is gone. Nothing is written. The event
            # waits in the queue and a replay asks again.
            if self._store.is_processed(event.id):
                return EventResult("duplicate")
            self._store.begin(event)
            self._store.add_dead_letter(event, str(failure))
            return EventResult("dead_lettered")
        result = self._handle_job(job, allow_unknown, None)
        if job.id != event.id:
            # The event is now the account job. A queued copy of the event itself is a leftover.
            self._store.remove_dead_letter(event.id)
        return result

    def _handle_job(self, event: Event, allow_unknown: bool, planned: tuple[Action, ...] | None) -> EventResult:
        if self._store.is_processed(event.id):
            # A row left in the queue is a leftover. It would make every replay look failed.
            self._store.remove_dead_letter(event.id)
            return EventResult("duplicate")
        if event.type in JOB_TYPES:
            # Every step of an account job may be repeated: a repeated call gets the same reply
            # (docs/sozlesmeler.md, section 7). So a queued job runs again from its first step that
            # is not finished (H-5). Every caller claims the job first. The claim also checks, in
            # the same database step, that the job is not finished (inceleme 18).
            # The count and spacing limits apply to every resend (inceleme 19), so a job is not
            # hammered. One case needs no limit: every step is recorded as finished and only the
            # final record is missing. Nothing is sent to a target then. A human replay
            # (`allow_unknown`) skips the limits.
            limited = not allow_unknown and bool(self._pending(event, self._plan(event)))
            return self._run_claimed(event, planned, limited=limited)
        if not allow_unknown and self._store.dead_letter_state(event.id) == "unknown":
            # The event came again but its earlier outcome is unknown. No blind repeat.
            return EventResult("unknown")
        return self._execute_job(event, planned)

    def _execute_job(self, event: Event, planned: tuple[Action, ...] | None) -> EventResult:
        """Run the pending steps and record the outcome. The caller decided that the event may run."""
        # Keep the accepted event on record before any work. A crash must not lose it.
        self._store.begin(event)
        try:
            names = self._run(event, planned)
        except _Failed as failure:
            # An event with an unknown outcome is not counted as processed (docs/sozlesmeler.md, section 10).
            state = "unknown" if failure.unknown else "failed"
            self._store.add_dead_letter(event, str(failure), state=state)
            return EventResult("unknown" if failure.unknown else "dead_lettered")
        # A finished account job and the cleanup of the account's id are one transaction.
        # The job's own id is a keyed digest, so the finished record does not name the user.
        forget = event.user_id if event.type in JOB_TYPES else None
        self._store.mark_processed(event.id, "processed", forget_subject=forget)
        return EventResult("processed", actions=tuple(names))

    def _run_claimed(self, job: Event, planned: tuple[Action, ...] | None, *, limited: bool) -> EventResult:
        """Claim an account job, run it and end the claim. The caller may or may not hold the work lock.

        After an unknown outcome the claim is kept until it runs out: the target may still work
        on the call that timed out, so no second call is sent meanwhile (inceleme 18).
        """
        claim = self._store.claim_repeat(
            job.id,
            hold=self._hold(),
            max_attempts=SETTLE_MAX_ATTEMPTS if limited else None,
            min_interval=SETTLE_INTERVAL_SECONDS if limited else 0.0,
        )
        if claim == "done":
            # Another caller finished the job meanwhile. A row left in the queue is a leftover.
            self._store.remove_dead_letter(job.id)
            return EventResult("duplicate")
        if claim != "claimed":
            # Busy or limited: the job stays queued as it is. The reply names its queue state.
            state = self._store.dead_letter_state(job.id)
            return EventResult("dead_lettered" if state == "failed" else "unknown")
        result: EventResult | None = None
        try:
            result = self._execute_job(job, planned)
            return result
        finally:
            # An error that escapes here comes from the store, not from an open target call.
            if result is None or result.status != "unknown":
                self._release(job.id)

    def _hold(self) -> float:
        """How long a claim lasts: the longest wait for one target call, plus a margin."""
        return self._anonymize_timeout + REPEAT_HOLD_MARGIN_SECONDS

    def _release(self, job_id: str) -> None:
        try:
            self._store.release_repeat(job_id)
        except (sqlite3.Error, Busy):
            pass  # the claim then ends by itself when its hold runs out

    def settle_queued_jobs(self) -> list[tuple[str, EventResult]]:
        """Continue queued account deletion jobs while an event is handled (H-5). No scheduler is involved.

        Everything here ends at one deadline, `SETTLE_BUDGET_SECONDS` from the start: the queue
        read, the claims, every network read and every retry pause (inceleme 18). Only the record
        of an outcome may be written after it. The work lock is not taken: targets are called
        without it. The claim of each job keeps every other caller away from that job.
        The database picks at most `SETTLE_MAX_JOBS` jobs that may be tried now, so a long queue
        is never read in full. One job is tried at most `SETTLE_MAX_ATTEMPTS` times, at least
        `SETTLE_INTERVAL_SECONDS` apart. After that a human decides.
        """
        results: list[tuple[str, EventResult]] = []
        with deadline(SETTLE_BUDGET_SECONDS, grace=RECORD_GRACE_SECONDS):
            try:
                letters = self._store.repeatable_jobs(
                    limit=SETTLE_MAX_JOBS, max_attempts=SETTLE_MAX_ATTEMPTS, min_interval=SETTLE_INTERVAL_SECONDS
                )
                for letter in letters:
                    if not remaining():
                        break
                    results.append((letter.event.id, self._run_claimed(letter.event, None, limited=True)))
            except Busy:
                pass  # the time ran out while waiting for the database; the next event goes on
        return results

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
            results: ReplayResults = []
            for letter in letters:
                # The queue was read once, before the loop. An earlier event of this run may have
                # removed this record. The database decides, not the copy in memory.
                if self._store.dead_letter_state(letter.event.id) is None:
                    results.append((letter.event.id, EventResult("duplicate")))
                else:
                    results.append((letter.event.id, self.handle(letter.event, allow_unknown=include_unknown)))
            return self._ordered(results + skipped)
        with self._store.work_lock():
            previews, plans = self._replay_previews(include_unknown)
            if digest_of(replay_report(self._ordered(previews)), self._digest_key) != expected_digest:
                raise PreviewChanged
            letters, skipped = self._letters(include_unknown)
            results = []
            for letter in letters:
                plan = plans.get(letter.event.id)
                if self._store.dead_letter_state(letter.event.id) is None:
                    # Removed by an earlier event of this run, for example by the deletion job
                    # of the same account. It is not run and not recorded again.
                    results.append((letter.event.id, EventResult("duplicate")))
                elif plan is None:
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

    def _replay_previews(self, include_unknown: bool) -> tuple[ReplayResults, dict[str, _Planned]]:
        letters, skipped = self._letters(include_unknown)
        previews: ReplayResults = []
        plans: dict[str, _Planned] = {}
        for letter in letters:
            result, planned = self._preview(letter.event)
            previews.append((letter.event.id, result))
            if planned is not None:
                plans[letter.event.id] = planned
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
        if event.type in JOB_TYPES:
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
        # Keep the plan's type: an ordered plan must stay ordered.
        return type(actions)(self._resolve(action) for action in actions)

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
            ordered = isinstance(actions, OrderedPlan)
            pending = self._pending(event, actions)
            if pending and pass_number == 1:
                # From the first external write on, a crash leaves the outcome unknown.
                self._store.mark_writing(event.id)
            failures: list[str] = []
            unknown = False
            for action in pending:
                preview = action.preview()
                label = f"{preview.operation} {preview.target}"
                try:
                    self._retry(label, lambda action=action, label=label: self._attempt(event, action, label))
                except _Failed as failure:
                    failures.append(str(failure))
                except UnknownOutcome:
                    # Unknown outcome. No blind repeat.
                    failures.append(f"{label}: unknown outcome")
                    unknown = True
                else:
                    names.append(preview.operation)
                    if ordered:
                        # Recorded after every step, so a retry never calls a finished step again.
                        self._store.add_progress(event.id, self._step_key(action))
                    continue
                if ordered:
                    # The steps of an ordered plan depend on each other. Nothing runs after a
                    # step that is not done. For example nothing is anonymized while phone
                    # installations remain, and the Keycloak user is not deleted.
                    break
                # In a plain plan a failed step does not stop the others. For example the user is
                # still disabled on every tenant when Press does not answer.
            if failures:
                raise _Failed("; ".join(failures), unknown=unknown)
            if not any(isinstance(action, EnsureOrganization) for action in actions):
                return names
        raise _Failed("keycloak.ensure_organization: membership not visible yet")

    def _attempt(self, event: Event, action: Action, label: str) -> None:
        """One network attempt of one step. A retry after a 409 or a 5xx is a new attempt.

        For an account job the claim is extended right before every attempt, so it outlasts that
        call even when the call starts late (inceleme 19 and 20).
        """
        if event.type in JOB_TYPES:
            try:
                self._store.extend_repeat(event.id, hold=self._hold())
            except Busy:
                raise _Failed(f"{label}: deadline passed") from None
        self._execute(action)

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
        # Not reachable while every action type has a branch above.
        else:  # pragma: no cover
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
            pause = _BACKOFF_SECONDS * 2 ** (attempt - 1)
            left = remaining()
            # A pause never runs past the deadline (inceleme 18). Without time for another try, give up.
            if not transient or attempt == self._max_attempts or (left is not None and left <= pause):
                raise _Failed(f"{label}: {reason}")
            self._sleep(pause)
        raise _Failed(f"{label}: no attempt made")
