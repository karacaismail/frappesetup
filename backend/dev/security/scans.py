"""Manually invoked defensive checks and local release records."""

import argparse
import hashlib
import http.client
import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / ".pane/prompts/security-results"
SECURITY = Path("backend/dev/security")
FIXTURES = SECURITY / "fixtures"
OSV_CONFIG = SECURITY / "osv-exceptions.toml"
VERSIONS = dict(line.split("=", 1) for line in (ROOT / SECURITY / "tool-versions.env").read_text().splitlines())
BANDIT = VERSIONS["BANDIT_VERSION"]
OSV = VERSIONS["OSV_VERSION"]


@dataclass(frozen=True)
class Result:
    tool: str
    version: str
    command: str
    status: str
    required: bool = True
    findings: tuple = ()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def source_state():
    return {"commit": git("rev-parse", "HEAD").strip(),
            "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
            "dirty": bool(git("status", "--porcelain"))}


def save(directory, name, results, source=None):
    directory.mkdir(parents=True, exist_ok=True)
    metadata = source if source is not None else source_state()
    payload = {**metadata, "utc": datetime.now(timezone.utc).isoformat(),
               "results": [asdict(result) for result in results]}
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as record:
        json.dump(payload, record)
    temporary = Path(record.name)
    try:
        temporary.replace(directory / f"{name}.json")
    finally:
        temporary.unlink(missing_ok=True)


def read_record(directory, name):
    path = directory / f"{name}.json"
    if not path.exists():
        return {}
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def load_results(directory):
    current = source_state()
    for name, command in (("full", "security-full"), ("local", "dast-scan")):
        record = read_record(directory, name)
        results = [Result(**entry) for entry in record.get("results", [])]
        if not results:
            yield Result(command, "—", f"backend/dev/bin/{command}", "not_run")
            continue
        matches = all(record.get(key) == current[key] for key in ("commit", "dirty"))
        yield from (result if matches else replace(result, status="not_run", findings=()) for result in results)


def report(directory):
    lines = ["# Güvenlik taraması sonuçları", ""]
    for name in ("full", "local"):
        record = read_record(directory, name)
        if record:
            state = "değişiklik var" if record["dirty"] else "temiz"
            lines.append(f"- `{name}` · `{record['commit']}` · `{record.get('branch', '—')}` · "
                         f"`{record['utc']}` · Çalışma ağacı {state}.")
    lines.extend(["", "| Araç | Sürüm | Komut | Sonuç |", "| --- | --- | --- | --- |"])
    results = list(load_results(directory))
    for result in results:
        lines.append(f"| {result.tool} | {result.version} | `{result.command}` | `{result.status}` |")
    for result in results:
        if result.findings:
            lines.extend(["", f"## {result.tool}", ""])
            lines.extend(f"- {finding}" for finding in result.findings)
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


def valid_exception(item, today):
    try:
        expiry = item["ignoreUntil"]
        if isinstance(expiry, str):
            expiry = date.fromisoformat(expiry)
        return all(item[key].strip() for key in ("owner", "reason")) and expiry >= today
    except (KeyError, AttributeError, TypeError, ValueError):
        return False


def run_json(command):
    process = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    return process.returncode, json.loads(process.stdout)


def bandit_findings(command, paths):
    all_findings = []
    for start in range(0, len(paths), 100):
        code, report = run_json([*command, *paths[start:start + 100]])
        if code not in (0, 1) or report["errors"] or (code == 1 and not report["results"]):
            raise ValueError("Bandit did not complete.")
        all_findings.extend(report["results"])
    return all_findings


def scan_bandit():
    command = ["uvx", "--python", "3.12", "--exclude-newer", VERSIONS["TOOL_CUTOFF"],
               f"bandit@{BANDIT}", "-q", "-f", "json"]
    result = Result("Bandit", BANDIT, shlex.join(command) + " TRACKED_PYTHON_FILES", "fail")
    try:
        fixture = bandit_findings(command, [str(FIXTURES / "bandit.py")])
        if not any(item["test_id"] == "B101" and item["line_number"] == 1 for item in fixture):
            raise ValueError("Bandit missed its fixture.")
        entries = json.loads((ROOT / SECURITY / "bandit-exceptions.json").read_text())
        today = datetime.now(timezone.utc).date()
        if any(not valid_exception(item, today) for item in entries):
            raise ValueError("Invalid or expired Bandit exception.")
        keys = {(item["rule"], item["file"], item["line"]) for item in entries}
        files = [path for path in git("ls-files", "-z", "--", "backend").split("\0")
                 if path.endswith(".py") and not path.startswith(
                     ("backend/dev/guvenlik/fixtures/", f"{FIXTURES}/"))
                 and (ROOT / path).is_file() and not (ROOT / path).is_symlink()]
        if not files:
            raise ValueError("No tracked Python files to scan.")
        findings = {(item["test_id"], Path(item["filename"]).as_posix(), item["line_number"])
                    for item in bandit_findings(command, files)}
        unreviewed = tuple(f"{rule} · {filename}:{line}" for rule, filename, line in sorted(findings - keys))
        unused = tuple(f"Unused exception · {rule} · {filename}:{line}"
                       for rule, filename, line in sorted(keys - findings))
        for finding in (*unreviewed, *unused):
            print(f"Bandit: {finding}")
        return replace(result, status="fail" if unreviewed or unused else "pass",
                       findings=(*unreviewed, *unused))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Bandit check failed: {error}")
        return result


def dependency_locks(files):
    return [path for path in files if not path.startswith(f"{FIXTURES}/")
            and Path(path).name in {"requirements.txt", "package-lock.json", "uv.lock",
                                    "poetry.lock", "Pipfile.lock", "pnpm-lock.yaml", "yarn.lock"}]


def python_manifests():
    prefixes = ("backend/apps/", "backend/identity/identity_sync/", "backend/libs/oidc_verify/")
    return sorted(path for path in git("ls-files", "-z").split("\0")
                  if path.startswith(prefixes) and Path(path).name == "pyproject.toml")


def manifest_digest(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode() + b"\0" + (ROOT / path).read_bytes() + b"\0")
    return digest.hexdigest()


def compile_lock():
    import tomllib

    manifests = python_manifests()
    if not manifests:
        raise ValueError("No tracked Python project manifests.")
    projects = [tomllib.loads((ROOT / path).read_text()) for path in manifests]
    local_projects = {item["project"]["name"].lower().replace("_", "-") for item in projects}
    requirements = {requirement for item in projects
                    for requirement in item["project"].get("dependencies", [])}
    external = sorted(requirement for requirement in requirements
                      if re.match(r"[\w.-]+", requirement)[0].lower().replace("_", "-") not in local_projects)
    command = ["uv", "pip", "compile", "--universal", "--python-version", "3.14",
               "--exclude-newer", VERSIONS["TOOL_CUTOFF"], "--no-header", "--no-annotate", "-"]
    output = subprocess.check_output(command, cwd=ROOT, input="\n".join(external) + "\n", text=True)
    header = (f"# Regenerate with backend/dev/security/compile-lock.\n"
              f"# Manifest SHA256: {manifest_digest(manifests)}\n")
    (ROOT / SECURITY / "requirements.txt").write_text(header + output)


def verify_python_lock(locks):
    lock = SECURITY / "requirements.txt"
    if str(lock) not in locks:
        raise ValueError("Tracked backend Python dependency lock is missing.")
    expected = f"# Manifest SHA256: {manifest_digest(python_manifests())}"
    if expected not in (ROOT / lock).read_text().splitlines():
        raise ValueError("Python dependency lock is stale. Run backend/dev/security/compile-lock.")


def validate_osv_inputs(locks):
    import tomllib

    today = datetime.now(timezone.utc).date()
    config = tomllib.loads((ROOT / OSV_CONFIG).read_text())
    if set(config) - {"IgnoredVulns"}:
        raise ValueError("OSV may only ignore individual vulnerability IDs.")
    for item in config.get("IgnoredVulns", []):
        if (not item.get("id") or not valid_exception(item, today)
                or str(item["ignoreUntil"]) != str(item.get("effectiveUntil"))):
            raise ValueError("OSV exceptions require id, owner, reason and matching expiry dates.")
    cache = Path(os.environ["OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"]) / "osv-scalibr"
    ecosystems = {"PyPI"}
    if any(Path(path).name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"} for path in locks):
        ecosystems.add("npm")
    now = datetime.now(timezone.utc)
    for ecosystem in sorted(ecosystems):
        database = cache / ecosystem / "all.zip"
        updated = datetime.fromtimestamp(database.stat().st_mtime, timezone.utc)
        if not now - timedelta(days=7) <= updated <= now:
            raise ValueError(f"OSV {ecosystem} database must be downloaded within the last seven days.")


def scan_dependencies(requirements=None):
    command = ["osv-scanner", "scan", "source", "--offline", "--format", "json",
               "--config", str(OSV_CONFIG)]
    locks = dependency_locks(git("ls-files", "-z").split("\0"))
    result = Result("OSV-Scanner", OSV, shlex.join(command) + " LOCKFILES", "fail")
    try:
        if not locks:
            raise ValueError("No tracked dependency lock files.")
        verify_python_lock(locks)
        if requirements is not None:
            locks.append(str(requirements))
        output = subprocess.check_output(["osv-scanner", "--version"], text=True, cwd=ROOT)
        if not re.search(rf"(?m)^osv-scanner version: v?{re.escape(OSV)}\s*$", output, re.IGNORECASE):
            raise ValueError(f"OSV-Scanner {OSV} is required.")
        validate_osv_inputs(locks)
        fixture_command = ["osv-scanner", "scan", "source", "--offline", "--format", "json",
                           "--lockfile", str(FIXTURES / "requirements.txt")]
        code, fixture = run_json(fixture_command)
        ids = {vulnerability["id"] for source in fixture.get("results", [])
               for package in source["packages"] for vulnerability in package["vulnerabilities"]}
        if code != 1 or "GHSA-hmr4-m2h5-33qx" not in ids:
            raise ValueError("OSV missed its fixture.")
        actual = [*command, *(arg for lock in locks for arg in ("--lockfile", lock))]
        code, report = run_json(actual)
        if code not in (0, 1):
            raise ValueError(f"OSV exited with code {code}.")
        findings = set()
        for source in report["results"]:
            file = Path(source["source"]["path"])
            if file.is_absolute():
                file = file.relative_to(ROOT) if file.is_relative_to(ROOT) else Path(file.name)
            for entry in source["packages"]:
                package = entry["package"]
                for vulnerability in entry["vulnerabilities"]:
                    findings.add(f"{file} · {package['name']} {package['version']} · {vulnerability['id']}")
        if code == 1 and not findings:
            raise ValueError("OSV returned no findings for a failed scan.")
        for finding in sorted(findings):
            print(f"OSV: {finding}")
        return replace(result, status="fail" if findings else "pass", findings=tuple(sorted(findings)))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"OSV check failed: {error}")
        return result


def exit_status(results, *, ci):
    return int(any(result.status == "fail" or (ci and result.required and result.status == "not_run")
                   for result in results))


def runtime_inventory(image):
    command = [str(SECURITY / "runtime-packages"), "IMAGE_ID"]
    result = Result("Frappe runtime inventory", "pip", shlex.join(command), "not_run", required=False)
    if image is None:
        return result
    try:
        code, packages = run_json([command[0], image])
        if code != 0 or not isinstance(packages, list) or not packages:
            raise ValueError("Empty or failed runtime inventory.")
        print(f"Frappe runtime: {image} ({len(packages)} packages)")
        for package in packages:
            print(f"{package['name']}=={package['version']}")
        return replace(result, status="pass")
    except (OSError, ValueError, KeyError) as error:
        print(f"Frappe runtime inventory failed: {error}")
        return replace(result, status="fail")


def scan_full(requirements, *, ci=False, runtime_image=None):
    source = source_state()
    save(RESULTS, "full", [], source)
    results = [
        run("Security tool tests", "Python", ["python3", "-B", "-m", "unittest", "discover",
                                               "-s", str(SECURITY)]),
        run("Backend gate", f"Semgrep {VERSIONS['SEMGREP_VERSION']} / Gitleaks {VERSIONS['GITLEAKS_VERSION']}",
            ["backend/dev/bin/guvenlik-denetimi"]),
        scan_bandit(),
        run("Gitleaks", VERSIONS["GITLEAKS_VERSION"], [str(SECURITY / "history-scan")]),
        scan_dependencies(requirements),
        runtime_inventory(runtime_image),
        Result("Live API contract checks", "—", "—", "not_run"),
    ]
    save(RESULTS, "full", results, source)
    return exit_status(results, ci=ci)


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


def scan_local(target, *, ci=False):
    source = source_state()
    save(RESULTS, "local", [], source)
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
    except ConnectionRefusedError:
        print("Local site is not listening.")
        status = "not_run"
    except (OSError, http.client.HTTPException) as error:
        print(f"Local check failed: {error}")
        status = "fail"
    finally:
        connection.close()
    results = [Result("Local HTTP header check", "1", "backend/dev/bin/dast-scan LOCAL_URL", status),
               Result("ZAP Baseline", "—", "—", "not_run")]
    save(RESULTS, "local", results, source)
    return exit_status(results, ci=ci)


def main():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="mode", required=True)
    full = subcommands.add_parser("full")
    full.add_argument("--requirements", type=lambda value: Path(value).resolve())
    full.add_argument("--runtime-image")
    local = subcommands.add_parser("local")
    local.add_argument("target")
    for scan in (full, local):
        scan.add_argument("--ci", action="store_true", default=os.environ.get("CI", "").lower() in ("1", "true"))
    subcommands.add_parser("report")
    subcommands.add_parser("compile-lock")
    card = subcommands.add_parser("scorecard")
    card.add_argument("--open-findings", type=nonnegative_count)
    card.add_argument("--package-vulnerabilities", type=nonnegative_count)
    card.add_argument("--rejected-requests", type=nonnegative_count)
    args = parser.parse_args()
    if args.mode == "full":
        return scan_full(args.requirements, ci=args.ci, runtime_image=args.runtime_image)
    if args.mode == "local":
        try:
            return scan_local(args.target, ci=args.ci)
        except ValueError as error:
            parser.error(str(error))
    if args.mode == "compile-lock":
        compile_lock()
        return 0
    if args.mode == "scorecard":
        print(scorecard(RESULTS, open_findings=args.open_findings,
                        package_vulnerabilities=args.package_vulnerabilities,
                        rejected_requests=args.rejected_requests))
    else:
        print(report(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
