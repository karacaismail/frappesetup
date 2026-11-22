"""Run the O-31 mobile HTTP benchmark and append a Markdown report."""

import argparse
import json
import os
from contextlib import contextmanager
from math import ceil
from pathlib import Path
from statistics import median
from threading import Thread
from time import perf_counter_ns
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

import frappe
from frappe.app import application
from platform_core.api import mobile
from platform_core.mobil.protocol import PAGE_SIZE
from platform_core.mobil.tests.loopback_http import open_loopback
from werkzeug.serving import make_server

from . import fixture
from .performance_data import BACKLOG, EMPLOYEES, LEAVE_PER_EMPLOYEE, seed_backlog, seed_site, verify_counts

LIMITS_MS = {"v1_register": 1000, "v1_push": 1000, "v1_pull": 500, "v1_activity": 1000, "v1_pull (1000)": 500}
TIMING_HEADER = "X-Mobile-Test-Server-Ns"
SAMPLES = 50


def timed_application(environ, start_response):
    started = perf_counter_ns()

    def timed_response(status, headers, exc_info=None):
        return start_response(status, [*headers, (TIMING_HEADER, str(perf_counter_ns() - started))], exc_info)

    return application(environ, timed_response)


@contextmanager
def benchmark_server(phones, *, threaded=True):
    auth = {f"Bearer {phone.token}": phone.account for phone in phones}
    original_override = frappe.override_whitelisted_method

    def resolve(method):
        if method.startswith("platform_core.api.mobile."):
            return method
        return original_override(method)

    # Use the real Website User gate and original routes. Only the business adapter is synthetic.
    with (
        patch.dict(fixture.TOKENS, auth),
        patch.object(frappe, "override_whitelisted_method", resolve),
        patch.object(mobile, "COMMANDS", {"fixture.update": fixture.FixtureCommand("update")}),
        patch.object(mobile, "PROJECTIONS", {"fixture": fixture.projection}),
        patch.object(mobile, "INVENTORIES", {"fixture": fixture.scan_inventory}),
    ):
        server = make_server("127.0.0.1", 0, timed_application, threaded=threaded)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            worker.join()
            server.server_close()


def mobile_request(url, phone, endpoint, payload=None):
    return Request(
        f"{url}/api/method/platform_core.api.mobile.{endpoint}",
        data=json.dumps({"installation_id": phone.installation, **(payload or {})}).encode(),
        headers={
            "Authorization": f"Bearer {phone.token}",
            "Content-Type": "application/json",
            "X-Frappe-Site-Name": fixture.SITE,
            "X-Mobile-App-Version": "1.0.0",
            "X-Mobile-Contract-Version": "1",
            "X-Mobile-Test-Sid": phone.sid,
        },
        method="POST",
    )


def call(url, phone, endpoint, payload=None):
    request = mobile_request(url, phone, endpoint, payload)
    started = perf_counter_ns()
    try:
        with open_loopback(request, timeout=15) as response:
            message = json.load(response)["message"]
            server_ns = int(response.headers[TIMING_HEADER])
    except HTTPError as error:
        with error:
            raise RuntimeError(f"{endpoint} returned HTTP {error.code}.") from None
    elapsed_ns = perf_counter_ns() - started
    return message, (server_ns / 1e6, elapsed_ns / 1e6)


def measure_base(url, phones):
    samples = {endpoint: [] for endpoint in LIMITS_MS}
    for phone in phones:
        message, timing = call(url, phone, "v1_register")
        if message != {"installation_id": phone.installation}:
            raise RuntimeError("Registration did not bind the expected installation.")
        samples["v1_register"].append(timing)

    verify_counts()
    for phone in phones:
        operation_id = str(uuid4())
        operation = {
            "operation_id": operation_id,
            "command": "fixture.update",
            "record_id": phone.record,
            "version": phone.version,
            "fields": {"title": "Updated test leave"},
        }
        message, timing = call(url, phone, "v1_push", {"operations": [operation]})
        if message["operations"] != [{"operation_id": operation_id, "status": "applied"}]:
            raise RuntimeError("The benchmark update did not commit.")
        samples["v1_push"].append(timing)
        message, timing = call(url, phone, "v1_pull")
        if len(message["changes"]) != LEAVE_PER_EMPLOYEE or message["has_more"]:
            raise RuntimeError("Initial pull did not return the expected leave projection.")
        samples["v1_pull"].append(timing)
        message, timing = call(url, phone, "v1_activity")
        if not isinstance(message["last_user_activity_at"], int):
            raise RuntimeError("Activity was not recorded.")
        samples["v1_activity"].append(timing)
    return samples


def measure_backlog(url, phone, sample_count):
    baseline, _unused = call(url, phone, "v1_pull")
    if baseline["has_more"] or len(baseline["changes"]) != LEAVE_PER_EMPLOYEE:
        raise RuntimeError("The backlog phone needs a completed initial pull.")
    seed_backlog(phone)
    measured = []
    catchups = []
    while len(measured) < sample_count:
        cursor = baseline["cursor"]
        seen = set()
        elapsed = 0.0
        for _unused in range(ceil(BACKLOG / PAGE_SIZE)):
            message, timing = call(url, phone, "v1_pull", {"cursor": cursor})
            measured.append(timing)
            elapsed += timing[0]
            seen.update(change["record_id"] for change in message["changes"])
            cursor = message["cursor"]
            if not message["has_more"]:
                break
        if len(seen) != BACKLOG or message["has_more"]:
            raise RuntimeError("A catch-up run did not return exactly 1000 changes.")
        catchups.append(elapsed)
    return measured, catchups


def p95(values):
    return sorted(values)[ceil(len(values) * 0.95) - 1]


def report(samples, catchups, label):
    import erpnext
    import hrms

    rows = [
        f"### O-31 mobil ölçümü ({label})",
        "",
        f"Frappe {frappe.__version__}, ERPNext {erpnext.__version__}, HRMS {hrms.__version__}.",
        f"Örnek veri {EMPLOYEES} çalışan, 2.000 izin kaydı ve {EMPLOYEES} kurulum.",
        "İzin kayıtları HRMS tablolarında. Mobil uçlar örnek izin görünümünü kullandı.",
        "İstekler sıralı gönderildi. Sunucu süresi, sunucu çağrısından yanıt başlıklarına kadar ölçüldü.",
        "Bu süre kimlik kancasını ve işlem kesinleşmesini kapsar.",
        "İstemci süresi yerel HTTP aktarımını ve JSON okumayı da kapsar.",
        f"Her birikim koşusunda aynı başlangıç imleciyle {BACKLOG} değişiklik çekildi.",
        "",
        "| Uç | İstek | Sunucu p50 (ms) | Sunucu p95 (ms) | İstemci p95 (ms) | Sınır (ms) | Sonuç |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    passed = True
    for name, limit in LIMITS_MS.items():
        server, client = zip(*samples[name], strict=True)
        server_p95 = p95(server)
        passed &= server_p95 <= limit
        result = "pass" if server_p95 <= limit else "fail"
        rows.append(
            f"| {name} | {len(server)} | {median(server):.1f} | {server_p95:.1f} "
            f"| {p95(client):.1f} | {limit} | {result} |"
        )
    rows.extend(
        ("", f"Tam birikim çekimi {len(catchups)} kez tamamlandı. Sunucu toplamı p95 {p95(catchups):.1f} ms.")
    )
    return "\n".join(rows), passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--label", default="Frappe geliştirme sitesi")
    args = parser.parse_args()
    destination = args.status_file.resolve()
    os.chdir("sites")
    phones = seed_site(SAMPLES)
    with benchmark_server(phones, threaded=False) as url:
        samples = measure_base(url, phones[:SAMPLES])
        samples["v1_pull (1000)"], catchups = measure_backlog(url, phones[-1], SAMPLES)
    summary, passed = report(samples, catchups, args.label)
    with destination.open("a", encoding="utf-8") as output:
        output.write(f"\n\n{summary}\n")
    print(summary)
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
