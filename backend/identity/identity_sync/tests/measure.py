"""Manual performance measurement of the service (PROJE-KAYDI.md, O-31).

Start it by hand from this package folder:

    python3 -m tests.measure

It is never scheduled. This service is not a Frappe site. Its development setup is the real
HTTP server of the service against fake Keycloak, Press and tenant servers on 127.0.0.1.
The command starts that setup, calls every endpoint of the contract and prints one JSON report.

Each endpoint is called `--samples` times one after another (default 50), then
`--concurrency` times at once (default 20). An endpoint with a preview and an execute form is
measured in both forms. The limits are p95 500 ms for a read and 1 second for a write.
The exit code is 1 when a limit is broken or a request failed.

The time is taken at the client, around the whole request. It is the server time plus the
loopback round trip, so it never flatters the server. The fake targets answer at once:
the numbers show the cost of this service, not of Keycloak, Press or a tenant site.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

from identity_sync.auth import TokenRejected
from identity_sync.events import Event
from identity_sync.server import make_server

from .fakes import ORG_ID, Recorded, Reply, Stack, keycloak_user
from .test_server import sign

READ_LIMIT_MS, WRITE_LIMIT_MS = 500, 1000
DEFAULT_SAMPLES, DEFAULT_CONCURRENCY, DEFAULT_USERS = 50, 20, 200
SITE, AGENT, PRESS = "site-kiraci1-service", "ai-agent", "press-service"


def percentile(values: Sequence[float], rank: int) -> float:
    """The nearest-rank percentile: the smallest value that covers `rank` percent of the calls."""
    ordered = sorted(values)
    return ordered[max(math.ceil(rank / 100 * len(ordered)), 1) - 1]


def judge(rows: list[dict[str, object]], *, read_limit_ms: float, write_limit_ms: float) -> dict[str, object]:
    """Compare the measured rows with the limits. A failed request fails the run, however fast it was."""
    judged = []
    for row in rows:
        limit = read_limit_ms if row["kind"] == "read" else write_limit_ms
        requests = int(row.get("concurrent_requests", 0)) or 1
        judged.append(
            {
                **row,
                "limit_ms": limit,
                "within_limit": float(row["p95_ms"]) <= limit,
                "concurrent_error_rate": int(row.get("concurrent_errors", 0)) / requests,
            }
        )
    # A conflict (409 by design, see `_measure`) is not an error and does not fail the run.
    passed = all(
        row["within_limit"] and not row.get("errors") and not row.get("concurrent_errors") for row in judged
    )
    return {"endpoints": judged, "passed": passed}


class _Bench:
    def __init__(self, users: int, requests_needed: int) -> None:
        self.stack = Stack()
        settings = self.stack.app.settings
        sites = frozenset({SITE})
        self.rate_limit_raised = requests_needed > settings.rate_limit
        self.stack.app.settings = dataclasses.replace(
            settings,
            preview_azp=frozenset({AGENT}),
            execute_azp=sites,
            session_azp=sites,
            deletion_azp=frozenset({PRESS}),
            rate_limit=max(settings.rate_limit, requests_needed),
        )
        self.keycloak, self.issuer = self.stack.keycloak, self.stack.issuer
        self.org = self.keycloak.add_organization(ORG_ID, "kiraci1")
        self.subjects = [f"u-{number:04d}" for number in range(users)]
        for subject in self.subjects:
            self.add_account(subject)
        self.keycloak.serve_directory()
        listed = self.stack.app.settings.known_azp

        def verifier(token: str) -> dict[str, object]:
            azp = token.removeprefix("token-of-")
            if azp not in listed:
                raise TokenRejected("unknown_client")
            return {"azp": azp}

        self.httpd = make_server(self.stack.app, verifier, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.counter = 0
        self.serve_users()
        self.serve_invitations()

    def add_account(self, subject: str) -> None:
        """One made-up account, in sync on Keycloak, Press and the tenant."""
        email = f"{subject}@example.test"
        self.keycloak.add_user(keycloak_user(subject=subject, email=email), [self.org])
        self.stack.press.seed_member(self.issuer, subject, email, ORG_ID)
        self.stack.tenant.seed_user(self.issuer, subject, email)

    def close(self) -> None:
        self.httpd.shutdown()
        self.thread.join(5)
        self.httpd.server_close()
        self.stack.close()

    def post(self, path: str, body: dict[str, object], azp: str) -> int:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer token-of-{azp}"}
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()
                return response.status
        except urllib.error.HTTPError as error:
            with error:
                return error.code

    def request(self, method: str, path: str, body: object, azp: str | None, headers: dict[str, str] | None = None) -> tuple[int, object]:
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        if azp is not None:
            all_headers["Authorization"] = f"Bearer token-of-{azp}"
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            with error:
                return error.code, None

    def call(self, method: str, path: str, body: object, azp: str | None) -> Callable[[], int]:
        return lambda: self.request(method, path, body, azp)[0]

    def serve_users(self) -> None:
        """Serve the Keycloak lists again after the accounts changed.

        One route answers both readers: reconcile pages through every user, and an invitation
        searches for one e-mail (the invited address is new, so the search finds nobody).
        """
        self.keycloak.serve_directory()

        def users(req: Recorded) -> Reply:
            if "email" in req.query:
                return 200, []
            first, size = int(req.query.get("first", ["0"])[0]), int(req.query.get("max", ["100"])[0])
            return 200, list(self.keycloak.users.values())[first : first + size]

        self.keycloak.on("GET", f"{self.keycloak.admin}/users", users)

    def fresh(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter:05d}"

    # --- one request of each kind; each call uses fresh data so that it does real work ---

    def health(self) -> Callable[[], int]:
        return self.call("GET", "/healthz", None, None)

    def event(self) -> Callable[[], int]:
        # A new member verified the e-mail: the service links the user on Press and on the tenant.
        subject = self.fresh("new")
        self.keycloak.add_user(keycloak_user(subject=subject, email=f"{subject}@example.test"), [self.org])
        payload = {"id": self.fresh("e"), "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 1, "user_id": subject}
        body = json.dumps(payload).encode()
        stamp = int(time.time())
        headers = {"X-Identity-Sync-Timestamp": str(stamp), "X-Identity-Sync-Signature": sign(body, stamp)}

        def send() -> int:
            request = urllib.request.Request(self.base + "/v1/events", data=body, method="POST", headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    response.read()
                    return 200 if response.status == 202 else response.status
            except urllib.error.HTTPError as error:
                with error:
                    return error.code

        return send

    def revoke_session(self) -> Callable[[], int]:
        subject, sid = self.subjects[self.counter % len(self.subjects)], self.fresh("sid")
        self.keycloak.add_session(subject, sid)
        return self.call("POST", "/v1/sessions/revoke", {"sid": sid, "subject": subject}, SITE)

    def delete_account(self) -> Callable[[], int]:
        # Accounts outside the sample set, so the sample keeps its size for the other endpoints.
        subject = self.fresh("gone")
        self.add_account(subject)
        body = {"issuer": self.issuer, "subject": subject, "reauthenticated_at": int(time.time())}
        return self.call("POST", "/v1/account-deletions", body, PRESS)

    def preview_reconcile(self) -> Callable[[], int]:
        return self.call("POST", "/v1/reconcile", {"dry_run": True}, AGENT)

    def execute_reconcile(self) -> Callable[[], int]:
        # One drift per call: a member of Keycloak who has no record on the tenant yet.
        subject = self.fresh("drift")
        self.keycloak.add_user(keycloak_user(subject=subject, email=f"{subject}@example.test"), [self.org])
        self.serve_users()
        _status, preview = self.request("POST", "/v1/reconcile", {"dry_run": True}, AGENT)
        body = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": self.fresh("onay")}
        return self.call("POST", "/v1/reconcile", body, SITE)

    def queue_event(self) -> None:
        subject = self.subjects[self.counter % len(self.subjects)]
        failed = Event(id=self.fresh("q"), kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=subject)
        self.stack.app.store.add_dead_letter(failed, "tenant.provision kiraci1: HTTP 503")

    def list_dead_letters(self) -> Callable[[], int]:
        return self.call("GET", "/v1/dead-letters", None, AGENT)

    def preview_replay(self) -> Callable[[], int]:
        return self.call("POST", "/v1/dead-letters/replay", {"dry_run": True}, AGENT)

    def execute_replay(self) -> Callable[[], int]:
        self.queue_event()
        _status, preview = self.request("POST", "/v1/dead-letters/replay", {"dry_run": True}, AGENT)
        body = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": self.fresh("onay")}
        return self.call("POST", "/v1/dead-letters/replay", body, SITE)

    def open_operation(self) -> str:
        operation_id = self.fresh("op")
        self.stack.app.store.operation_begin(operation_id, "invite_user", ORG_ID, ["keycloak.create_user"])
        return operation_id

    def list_operations(self) -> Callable[[], int]:
        return self.call("GET", "/v1/operations", None, AGENT)

    def resolve_operation(self) -> Callable[[], int]:
        return self.call("POST", f"/v1/operations/{self.open_operation()}/resolve", {"resolution": "abandoned"}, SITE)

    def invitation(self) -> dict[str, object]:
        return {"email": f"{self.fresh('invite')}@example.test", "organization_id": ORG_ID}

    def preview_invitation(self) -> Callable[[], int]:
        return self.call("POST", "/v1/invitations", {**self.invitation(), "dry_run": True}, SITE)

    def execute_invitation(self) -> Callable[[], int]:
        invitation = self.invitation()
        _status, preview = self.request("POST", "/v1/invitations", {**invitation, "dry_run": True}, SITE)
        body = {**invitation, "dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": self.fresh("onay")}
        return self.call("POST", "/v1/invitations", body, SITE)

    def serve_invitations(self) -> None:
        """Keycloak answers for an invitation: create the user, add the member, send the e-mail."""
        keycloak, admin = self.keycloak, self.keycloak.admin

        def create(_req: Recorded) -> Reply:
            new_id = self.fresh("invited")
            keycloak.on("PUT", f"{admin}/users/{new_id}/execute-actions-email", (204, None))
            return 201, None, {"Location": f"{keycloak.url}{admin}/users/{new_id}"}

        keycloak.on("POST", f"{admin}/users", create)
        keycloak.on("POST", f"{admin}/organizations/{ORG_ID}/members", (201, None))


# One approved plan runs at a time on these endpoints. See `_measure`.
ONE_AT_A_TIME = frozenset({"POST /v1/reconcile (execute)", "POST /v1/dead-letters/replay (execute)"})


def _measure(
    prepare: Callable[[], Callable[[], int]], samples: int, concurrency: int, *, one_at_a_time: bool = False
) -> dict[str, object]:
    """Call one endpoint `samples` times in a row, then `concurrency` times at once.

    `one_at_a_time`: the endpoint runs one approved plan at a time. Approvals given for the
    same preview cannot all run: once the first changed the state, the others get 409
    `preview_changed` by design and write nothing. Those are counted as conflicts, not as
    errors. At least one of the concurrent requests must still succeed.
    """
    durations: list[float] = []
    errors = 0
    for _ in range(samples):
        call = prepare()
        started = time.perf_counter()
        status = call()
        durations.append((time.perf_counter() - started) * 1000)
        errors += status != 200
    calls = [prepare() for _ in range(concurrency)]
    statuses: list[int] = []
    waits: list[float] = []
    gate = threading.Barrier(concurrency)

    def one(call: Callable[[], int]) -> None:
        gate.wait()
        begun = time.perf_counter()
        try:
            statuses.append(call())
        except OSError:
            statuses.append(0)  # the connection was refused, reset or timed out
        waits.append((time.perf_counter() - begun) * 1000)

    threads = [threading.Thread(target=one, args=(call,)) for call in calls]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return {
        "calls": samples,
        "errors": errors,
        "p50_ms": round(percentile(durations, 50), 2),
        "p95_ms": round(percentile(durations, 95), 2),
        "max_ms": round(max(durations), 2),
        "concurrent_requests": concurrency,
        "concurrent_errors": sum(status not in ((200, 409) if one_at_a_time else (200,)) for status in statuses)
        + (one_at_a_time and 200 not in statuses),
        "concurrent_conflicts": sum(status == 409 for status in statuses) if one_at_a_time else 0,
        "concurrent_total_ms": round((time.perf_counter() - started) * 1000, 2),
        # How long a caller waits when 20 arrive at once. The server handles one request at a
        # time, so this includes the queue. It is reported, not judged: the limit is server time.
        "concurrent_wait_p95_ms": round(percentile(waits, 95), 2),
    }


def run(
    *,
    samples: int = DEFAULT_SAMPLES,
    concurrency: int = DEFAULT_CONCURRENCY,
    users: int = DEFAULT_USERS,
    read_limit_ms: float = READ_LIMIT_MS,
    write_limit_ms: float = WRITE_LIMIT_MS,
) -> dict[str, object]:
    # Every row costs samples + concurrency requests. A row with an execute form costs a preview too.
    bench = _Bench(users, requests_needed=20 * (samples + concurrency))
    try:
        store = bench.stack.app.store
        plan: list[tuple[str, str, Callable[[], Callable[[], int]]]] = [
            ("GET /healthz", "read", bench.health),
            # The reads are measured first, on the untouched sample.
            ("POST /v1/reconcile (preview)", "read", bench.preview_reconcile),
            ("POST /v1/invitations (preview)", "read", bench.preview_invitation),
        ]
        rows = [{"endpoint": name, "kind": kind, **_measure(prepare, samples, concurrency)} for name, kind, prepare in plan]
        # The two list endpoints and the replay preview are measured on a filled queue and journal.
        for _ in range(50):
            bench.queue_event()
            bench.open_operation()
        filled = [
            ("GET /v1/dead-letters", "read", bench.list_dead_letters),
            ("GET /v1/operations", "read", bench.list_operations),
            ("POST /v1/dead-letters/replay (preview)", "read", bench.preview_replay),
        ]
        rows += [{"endpoint": name, "kind": kind, **_measure(prepare, samples, concurrency)} for name, kind, prepare in filled]
        for letter in store.dead_letters():
            store.remove_dead_letter(letter.event.id)
        writes = [
            ("POST /v1/dead-letters/replay (execute)", "write", bench.execute_replay),
            ("POST /v1/operations/{operation_id}/resolve", "write", bench.resolve_operation),
            ("POST /v1/events", "write", bench.event),
            ("POST /v1/invitations (execute)", "write", bench.execute_invitation),
            ("POST /v1/sessions/revoke", "write", bench.revoke_session),
            ("POST /v1/account-deletions", "write", bench.delete_account),
            # Last: every call adds one account to Keycloak, so the lists grow.
            ("POST /v1/reconcile (execute)", "write", bench.execute_reconcile),
        ]
        rows += [
            {"endpoint": name, "kind": kind, **_measure(prepare, samples, concurrency, one_at_a_time=name in ONE_AT_A_TIME)}
            for name, kind, prepare in writes
        ]
        report = judge(rows, read_limit_ms=read_limit_ms, write_limit_ms=write_limit_ms)
        return {
            "targets": "fake",
            "sample_data": {
                "keycloak_users": users,
                "press_identities": users,
                "tenant_identities": users,
                "queued_events_for_the_lists": 50,
                "open_operations_for_the_lists": 50,
            },
            "rate_limit_raised": bench.rate_limit_raised,
            "python": sys.version.split()[0],
            **report,
        }
    finally:
        bench.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m tests.measure", description=__doc__.split("\n\n")[0])
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES, help="Calls per endpoint, one after another.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Calls per endpoint at once.")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="Made-up accounts in the sample.")
    parser.add_argument("--read-limit-ms", type=float, default=READ_LIMIT_MS)
    parser.add_argument("--write-limit-ms", type=float, default=WRITE_LIMIT_MS)
    args = parser.parse_args(argv)
    if min(args.samples, args.concurrency, args.users) < 1:
        parser.error("--samples, --concurrency and --users must be at least 1")
    report = run(
        samples=args.samples,
        concurrency=args.concurrency,
        users=args.users,
        read_limit_ms=args.read_limit_ms,
        write_limit_ms=args.write_limit_ms,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
