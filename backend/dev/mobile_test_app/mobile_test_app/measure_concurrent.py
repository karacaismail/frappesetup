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

import frappe
from platform_core.mobil.tests.loopback_http import open_loopback

from .measure_performance import LIMITS_MS, TIMING_HEADER, benchmark_server, call, mobile_request, p95
from .performance_data import EMPLOYEES, LEAVE_PER_EMPLOYEE, performance_fixture, test_database, verify_counts

PHONES = 50
ENDPOINTS = ("v1_push", "v1_pull")


@dataclass(frozen=True)
class Sample:
    status: int | None
    ok: bool
    server_ms: float | None
    client_ms: float
    error_code: str = ""
    worker: str = ""
    db_failures: tuple[str, ...] = ()


def lock_counters(site):
    with test_database(site):
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
            body = json.load(response)
            message = body.get("message") or {}
        except ValueError:
            body = message = {}
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
            body.get("code") or message.get("code", ""),
            response.headers.get("X-Mobile-Test-Worker", ""),
            tuple(filter(None, response.headers.get("X-Mobile-Test-DB-Failures", "").split(","))),
        )


def measure(url, phones):
    requests = []
    for phone in phones:
        operation = {
            "operation_id": phone.operation_id,
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
    before = lock_counters(phones[0].site)
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        for endpoint, sample in pool.map(send, requests):
            samples[endpoint].append(sample)
    after = lock_counters(phones[0].site)
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
        workers = Counter(sample.worker for sample in values if sample.worker)
        errors_by_code = Counter(sample.error_code for sample in values if sample.error_code)
        failures = Counter(failure for sample in values for failure in sample.db_failures)
        status_lines.append(
            f"  İşçiler {dict(workers)}. Hata kodları {dict(errors_by_code)}."
            f" Veri tabanı hataları {dict(failures)}."
        )
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


def run_trial(site, workers):
    with performance_fixture(site, PHONES) as (phones, _created):
        phones = phones[:PHONES]
        with benchmark_server(phones, site=site, workers=workers) as url:
            for phone in phones:
                message, _unused = call(url, phone, "v1_register")
                if message != {"installation_id": phone.installation}:
                    raise RuntimeError("Registration did not bind the expected installation.")
            verify_counts(site)
            return measure(url, phones)


def recommend_worker_count(trials, client_limit_ms):
    for workers, measurements in sorted(trials.items()):
        if measurements and all(passed and elapsed <= client_limit_ms for passed, elapsed in measurements):
            return workers
    return None


def measure_capacity(site, candidates, repeats, client_limit_ms):
    rows = [
        "### Mobil Gunicorn işçi sayısı ölçümü",
        "",
        f"Her koşuda {PHONES} telefon aynı anda bir yazma ve bir okuma isteği gönderdi.",
        f"İşçi önerisi için istemci p95 üst sınırı {client_limit_ms:g} ms.",
        "O-31 sunucu sınırları ve sıfır hata koşulu da geçerli.",
        "",
        "| İşçi | Koşu | Uç | Sunucu p95 (ms) | İstemci p95 (ms) | Hata | Kilit bekleme (sayı ve ms) |",
        "| ---: | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    trials = {}
    for workers in sorted(set(candidates)):
        trials[workers] = []
        for iteration in range(1, repeats + 1):
            samples, locks = run_trial(site, workers)
            _unused, passed = render(samples, locks)
            client_times = []
            for endpoint, values in samples.items():
                server_times = [sample.server_ms for sample in values if sample.server_ms is not None]
                server = f"{p95(server_times):.1f}" if server_times else "ölçülmedi"
                client = p95([sample.client_ms for sample in values])
                client_times.append(client)
                errors = sum(not sample.ok for sample in values)
                rows.append(
                    f"| {workers} | {iteration} | {endpoint} | {server} | {client:.1f} "
                    f"| {errors}/{len(values)} | {locks[0]} / {locks[1]} |"
                )
            trials[workers].append((passed, max(client_times)))
    recommended = recommend_worker_count(trials, client_limit_ms)
    rows.extend(("", "Kilit bekleme değerleri her koşunun iki ucu için ortaktır."))
    if recommended is None:
        rows.append("İşçi önerisi yok. Ölçülen sayıların hiçbiri bütün koşulları karşılamadı.")
    else:
        rows.append(f"Bu ortam için başlangıç önerisi {recommended} Gunicorn işçisi.")
    return "\n".join(rows), recommended is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    worker_mode = parser.add_mutually_exclusive_group()
    worker_mode.add_argument("--workers", type=int, default=4)
    worker_mode.add_argument("--worker-candidates", type=int, nargs="+")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--client-p95-limit-ms", type=int, default=1000)
    args = parser.parse_args()
    if args.workers < 0 or any(workers < 1 for workers in (args.worker_candidates or [])):
        parser.error("Worker candidates must be positive. A single worker count may be zero.")
    if args.repeats < 1 or args.client_p95_limit_ms < 1:
        parser.error("Repeats and the client limit must be positive.")
    destination = args.status_file.resolve()
    os.chdir("sites")
    if args.worker_candidates:
        report, passed = measure_capacity(
            args.site, args.worker_candidates, args.repeats, args.client_p95_limit_ms
        )
    else:
        samples, locks = run_trial(args.site, args.workers)
        report, passed = render(samples, locks)
    with destination.open("a", encoding="utf-8") as output:
        output.write(f"\n\n{report}\n")
    print(report)
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
