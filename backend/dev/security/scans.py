"""Manually invoked defensive checks and local release records."""

import argparse
import http.client
import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / ".pane/prompts/security-results"
BANDIT = "1.9.4"
OSV_CONFIG = "backend/dev/security/osv-exceptions.toml"
OSV = "2.7.1"


@dataclass(frozen=True)
class Result:
    tool: str
    version: str
    command: str
    status: str


def save(directory, name, results):
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as record:
        json.dump([asdict(result) for result in results], record)
    temporary = Path(record.name)
    try:
        temporary.replace(directory / f"{name}.json")
    finally:
        temporary.unlink(missing_ok=True)


def load_results(directory):
    for name, command in (("full", "security-full"), ("local", "dast-scan")):
        path = directory / f"{name}.json"
        if path.exists():
            yield from (Result(**entry) for entry in json.loads(path.read_text()))
        else:
            yield Result(command, "—", f"backend/dev/bin/{command}", "not_run")


def report(directory):
    lines = ["# Güvenlik taraması sonuçları", "",
             "| Araç | Sürüm | Komut | Sonuç |", "| --- | --- | --- | --- |"]
    for result in load_results(directory):
        lines.append(f"| {result.tool} | {result.version} | `{result.command}` | `{result.status}` |")
    return "\n".join(lines)


def scorecard(directory, *, open_findings=None, package_vulnerabilities=None, rejected_requests=None):
    statuses = [result.status for result in load_results(directory)]
    rows = [
        ("Başarılı denetim", statuses.count("pass")),
        ("Başarısız denetim", statuses.count("fail")),
        ("Çalışmayan denetim", statuses.count("not_run")),
        ("Geçerli olmayan denetim", statuses.count("not_applicable")),
        ("Açık bulgu", open_findings),
        ("Paket açığı", package_vulnerabilities),
        ("Reddedilen istek", rejected_requests),
    ]
    lines = ["# Güvenlik karnesi", "", "| Ölçüm | Sayı |", "| --- | --- |"]
    for name, count in rows:
        value = "Ölçülmedi" if count is None else count
        lines.append(f"| {name} | {value} |")
    return "\n".join(lines)


def nonnegative_count(value):
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError("Expected a nonnegative count.")
    return count


def run(tool, version, command):
    print(f"Running {tool}: {shlex.join(command)}", flush=True)
    try:
        code = subprocess.run(command, cwd=ROOT, check=False).returncode
    except OSError as error:
        print(error)
        code = 1
    return Result(tool, version, shlex.join(command), "pass" if code == 0 else "fail")


def scan_dependencies(requirements):
    command = ["osv-scanner", "scan", "source", "--offline", "--config", OSV_CONFIG, "--lockfile"]
    recorded_command = shlex.join([*command, "REQUIREMENTS"])
    if requirements is None or not requirements.is_file():
        print("A pinned Python requirements.txt export is required for the dependency scan.")
        return Result("OSV-Scanner", OSV, "security-full --requirements requirements.txt", "not_run")
    try:
        output = subprocess.check_output(["osv-scanner", "--version"], text=True, cwd=ROOT)
    except (OSError, subprocess.CalledProcessError) as error:
        print(error)
        output = ""
    if not re.search(rf"(?m)^osv-scanner version: v?{re.escape(OSV)}\s*$", output, re.IGNORECASE):
        print(f"OSV-Scanner {OSV} is required.")
        return Result("OSV-Scanner", OSV, recorded_command, "fail")
    result = run("OSV-Scanner", OSV, [*command, str(requirements)])
    # Store a fixed command template to keep local paths out of shared reports.
    return Result(result.tool, result.version, recorded_command, result.status)


def scan_full(requirements):
    os.environ["SEMGREP_ENABLE_VERSION_CHECK"] = "0"
    results = [
        run("Backend gate", "Semgrep 1.186.0 / Gitleaks 8.30.1",
            ["backend/dev/bin/guvenlik-denetimi"]),
        run("Bandit", BANDIT, ["uvx", "--python", "3.12", f"bandit@{BANDIT}",
                               "-r", "backend", "-x", "backend/dev/guvenlik/fixtures"]),
        run("Gitleaks", "8.30.1", ["backend/dev/security/history-scan"]),
        scan_dependencies(requirements),
        Result("Live API contract checks", "—", "—", "not_run"),
    ]
    save(RESULTS, "full", results)
    return int(any(result.status != "pass" for result in results[:-1]))


def local_target(target):
    address = urlsplit(target)
    host = address.hostname or ""
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    allowed = host == "127.0.0.1" or re.fullmatch(rf"(?:{label}\.)+localhost", host)
    if (not allowed or address.scheme != "http" or address.username is not None
            or address.path not in ("", "/") or "?" in target or "#" in target
            or any(character.isspace() for character in target)):
        raise ValueError("Use a local HTTP root on 127.0.0.1 or *.localhost.")
    port = address.port
    if port == 0:
        raise ValueError("Use a port from 1 to 65535.")
    return host, port if port is not None else 80


def scan_local(target):
    host, port = local_target(target)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/", headers={"Host": f"{host}:{port}"})
        with connection.getresponse() as response:
            print(f"HTTP {response.status}")
            if response.status >= 500:
                status = "fail"
            elif response.getheader("X-Content-Type-Options", "").strip().lower() != "nosniff":
                print("Missing X-Content-Type-Options: nosniff")
                status = "fail"
            else:
                status = "pass"
    except (OSError, http.client.HTTPException) as error:
        print(f"Local check failed: {error}")
        status = "fail"
    finally:
        connection.close()
    save(RESULTS, "local", [Result("Local HTTP header check", "1",
                                   "backend/dev/bin/dast-scan LOCAL_URL", status),
                            Result("ZAP Baseline", "—", "—", "not_run")])
    return int(status == "fail")


def main():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="mode", required=True)
    full = subcommands.add_parser("full")
    full.add_argument("--requirements", type=lambda value: Path(value).resolve())
    local = subcommands.add_parser("local")
    local.add_argument("target")
    subcommands.add_parser("report")
    card = subcommands.add_parser("scorecard")
    card.add_argument("--open-findings", type=nonnegative_count)
    card.add_argument("--package-vulnerabilities", type=nonnegative_count)
    card.add_argument("--rejected-requests", type=nonnegative_count)
    args = parser.parse_args()
    if args.mode == "full":
        return scan_full(args.requirements)
    if args.mode == "local":
        try:
            return scan_local(args.target)
        except ValueError as error:
            parser.error(str(error))
    if args.mode == "scorecard":
        print(scorecard(RESULTS, open_findings=args.open_findings,
                        package_vulnerabilities=args.package_vulnerabilities,
                        rejected_requests=args.rejected_requests))
    else:
        print(report(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
