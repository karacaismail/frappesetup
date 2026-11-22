"""Manual performance measurement of the service (PROJE-KAYDI.md, O-31).

Start it by hand from this package folder:

    python3 -m tests.measure

It is never scheduled. It starts the real HTTP server of the service against fake Keycloak,
Press and tenant servers on 127.0.0.1, calls three endpoints and prints one JSON report:

- `POST /v1/sessions/revoke` (write),
- `POST /v1/account-deletions` (write, the whole five-step flow),
- `POST /v1/reconcile` with `dry_run: true` (read).

Each endpoint is called `--samples` times one after another (default 50), then
`--concurrency` times at once (default 20). The limits are p95 500 ms for a read and
1 second for a write. The exit code is 1 when a limit is broken or a request failed.

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
from identity_sync.server import make_server

from .fakes import ORG_ID, Stack, keycloak_user

READ_LIMIT_MS, WRITE_LIMIT_MS = 500, 1000
DEFAULT_SAMPLES, DEFAULT_CONCURRENCY, DEFAULT_USERS = 50, 20, 200
SITE, AGENT, PRESS = "site-kiraci1", "ai-agent", "press-service"


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
        self.sessions = 0
        self.extras = 0

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

    # --- one request of each kind; each call uses fresh data so that it does real work ---

    def revoke_session(self) -> Callable[[], int]:
        self.sessions += 1
        subject, sid = self.subjects[self.sessions % len(self.subjects)], f"sid-{self.sessions:05d}"
        self.keycloak.add_session(subject, sid)
        return lambda: self.post("/v1/sessions/revoke", {"sid": sid, "subject": subject}, SITE)

    def delete_account(self) -> Callable[[], int]:
        # Accounts outside the sample set, so the sample keeps its size for the other endpoints.
        self.extras += 1
        subject = f"gone-{self.extras:05d}"
        self.add_account(subject)
        body = {"issuer": self.issuer, "subject": subject, "reauthenticated_at": int(time.time())}
        return lambda: self.post("/v1/account-deletions", body, PRESS)

    def preview_reconcile(self) -> Callable[[], int]:
        return lambda: self.post("/v1/reconcile", {"dry_run": True}, AGENT)


def _measure(prepare: Callable[[], Callable[[], int]], samples: int, concurrency: int) -> dict[str, object]:
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
        "concurrent_errors": sum(status != 200 for status in statuses),
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
    bench = _Bench(users, requests_needed=3 * (samples + concurrency))
    try:
        plan = (
            # The read is measured first, on the untouched sample.
            ("POST /v1/reconcile (preview)", "read", bench.preview_reconcile),
            ("POST /v1/sessions/revoke", "write", bench.revoke_session),
            ("POST /v1/account-deletions", "write", bench.delete_account),
        )
        rows = [{"endpoint": name, "kind": kind, **_measure(prepare, samples, concurrency)} for name, kind, prepare in plan]
        report = judge(rows, read_limit_ms=read_limit_ms, write_limit_ms=write_limit_ms)
        return {
            "targets": "fake",
            "sample_data": {"keycloak_users": users, "press_identities": users, "tenant_identities": users},
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
