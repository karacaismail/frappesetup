"""Measure simultaneous mobile writes and reads for 50 fixture phones."""

import argparse
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier
from time import perf_counter_ns
from urllib.error import HTTPError, URLError
from uuid import uuid4

import frappe
from platform_core.mobil.tests.loopback_http import open_loopback

from .measure_performance import LIMITS_MS, TIMING_HEADER, benchmark_server, call, mobile_request, p95
from .performance_data import EMPLOYEES, LEAVE_PER_EMPLOYEE, seed_site, test_database, verify_counts

PHONES = 50
ENDPOINTS = ("v1_push", "v1_pull")


@dataclass(frozen=True)
class Sample:
    status: int | None
    ok: bool
    server_ms: float | None
    client_ms: float


def lock_counters():
    with test_database():
        # These fixed MariaDB status counters describe real InnoDB row-lock waits.
        rows = frappe.db.sql(
            "SHOW GLOBAL STATUS WHERE Variable_name IN ('Innodb_row_lock_waits', 'Innodb_row_lock_time')"
        )
    counters = {name.lower(): int(value) for name, value in rows}
    return counters["innodb_row_lock_waits"], counters["innodb_row_lock_time"]


def exchange(request, expected_updates):
    start = perf_counter_ns()
    try:
        response = open_loopback(request, timeout=20)
    except HTTPError as error:
        response = error
    except (URLError, TimeoutError):
        return Sample(None, False, None, (perf_counter_ns() - start) / 1e6)

    with response:
        try:
            message = json.load(response).get("message", {})
        except ValueError:
            message = {}
        measured_ns = response.headers.get(TIMING_HEADER)
        if expected_updates is not None:
            valid = message.get("operations") == expected_updates
        else:
            valid = len(message.get("changes", [])) == LEAVE_PER_EMPLOYEE and message.get("has_more") is False
        return Sample(
            response.status,
            response.status == 200 and valid,
            int(measured_ns) / 1e6 if measured_ns else None,
            (perf_counter_ns() - start) / 1e6,
        )


def measure(url, phones):
    requests = []
    for phone in phones:
        operation = {
            "operation_id": str(uuid4()),
            "command": "fixture.update",
            "record_id": phone.record,
            "version": phone.version,
            "fields": {"title": "Concurrent test leave"},
        }
        expected = [{"operation_id": operation["operation_id"], "status": "applied"}]
        requests.extend(
            (
                ("v1_push", mobile_request(url, phone, "v1_push", {"operations": [operation]}), expected),
                ("v1_pull", mobile_request(url, phone, "v1_pull"), None),
            )
        )

    ready = Barrier(len(requests), timeout=10)

    def send(item):
        endpoint, request, expected = item
        ready.wait()
        return endpoint, exchange(request, expected)

    samples = {method: [] for method in ENDPOINTS}
    before = lock_counters()
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        for endpoint, sample in pool.map(send, requests):
            samples[endpoint].append(sample)
    after = lock_counters()
    return samples, (after[0] - before[0], after[1] - before[1])


def render(samples, locks):
    waits, wait_ms = locks
    rows = [
        "### O-31 eşzamanlı mobil ölçümü",
        "",
        f"Örnek veri {EMPLOYEES} çalışan, 2.000 izin kaydı ve çalışan başına bir kurulum.",
        f"{PHONES} telefon, bir gönderme ve bir çekme isteğini birlikte başlattı.",
        "Sunucu süresi, istek girişinden yanıt başlıklarının hazır olmasına kadar ölçüldü.",
        "İstemci süresi yerel HTTP aktarımını ve yanıt okumayı da kapsar.",
        "",
        "| Uç | İstek | Sunucu p95 (ms) | İstemci p95 (ms) | Hata oranı | Sınır (ms) | Sonuç |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    status_lines = []
    passed = True
    for endpoint, values in samples.items():
        server_times = [sample.server_ms for sample in values if sample.server_ms is not None]
        client_p95 = p95([sample.client_ms for sample in values])
        server_p95 = p95(server_times) if server_times else None
        server_text = f"{server_p95:.1f}" if server_p95 is not None else "ölçülmedi"
        errors = sum(not sample.ok for sample in values)
        limit = LIMITS_MS[endpoint]
        statuses = Counter(sample.status for sample in values)
        passed_endpoint = not errors and len(server_times) == PHONES and server_p95 <= limit
        passed &= passed_endpoint
        result = "pass" if passed_endpoint else "fail"
        rows.append(
            f"| {endpoint} | {len(values)} | {server_text} | {client_p95:.1f} "
            f"| {errors}/{len(values)} (%{100 * errors / len(values):.1f}) | {limit} | {result} |"
        )
        status_lines.append(f"- `{endpoint}` HTTP sonuçları {dict(statuses)}.")
    rows.extend(
        (
            "",
            *status_lines,
            "",
            f"MariaDB toplam satır kilidi beklemesi {wait_ms} ms. Bekleme sayısı {waits}.",
            "Bu sayaçlar karışık yükün toplamıdır. Uçlara ayrı ayrı dağıtılmaz.",
        )
    )
    return "\n".join(rows), passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-file", type=Path, required=True)
    args = parser.parse_args()
    destination = args.status_file.resolve()
    os.chdir("sites")
    phones = seed_site(PHONES)
    with benchmark_server(phones[:PHONES]) as url:
        for phone in phones[:PHONES]:
            message, _unused = call(url, phone, "v1_register")
            if message != {"installation_id": phone.installation}:
                raise RuntimeError("Registration did not bind the expected installation.")
        verify_counts()
        samples, locks = measure(url, phones[:PHONES])
    report, passed = render(samples, locks)
    with destination.open("a", encoding="utf-8") as output:
        output.write(f"\n\n{report}\n")
    print(report)
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
