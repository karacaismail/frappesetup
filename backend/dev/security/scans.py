"""Manually invoked defensive checks and local release records."""

import argparse
import ast
import base64
import hashlib
import http.client
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / ".pane/prompts/security-results"
SECURITY = Path("backend/dev/security")
FIXTURES = SECURITY / "fixtures"
CONTRACT_FIXTURE = SECURITY / "contract-fixtures" / "contract.yaml"
OSV_CONFIG = SECURITY / "osv-exceptions.toml"
VERSIONS = dict(line.split("=", 1) for line in (ROOT / SECURITY / "tool-versions.env").read_text().splitlines())
BANDIT = VERSIONS["BANDIT_VERSION"]
OSV = VERSIONS["OSV_VERSION"]
SCHEMATHESIS = VERSIONS["SCHEMATHESIS_VERSION"]
CONTRACTS = Path("backend/contracts")
CONTRACT_CHECKS = ("not_a_server_error,status_code_conformance,content_type_conformance,"
                   "response_headers_conformance,response_schema_conformance")


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
        try:
            results = [Result(**entry) for entry in record.get("results", [])]
        except TypeError:
            results = []
        if not results:
            yield Result(command, "—", f"backend/dev/bin/{command}", "not_run")
            continue
        matches = (record.get("dirty") is False and current["dirty"] is False
                   and record.get("utc") and record.get("commit") == current["commit"])
        yield from (result if matches else replace(result, status="not_run", findings=()) for result in results)


def report(directory):
    lines = ["# Security scan results", ""]
    for name in ("full", "local"):
        record = read_record(directory, name)
        if record:
            dirty = record.get("dirty")
            state = "dirty" if dirty is True else "clean" if dirty is False else "unknown"
            lines.append(f"- {markdown_code(name)} · {markdown_code(record.get('commit', '—'))} · "
                         f"{markdown_code(record.get('branch', '—'))} · {markdown_code(record.get('utc', '—'))} · Working tree: {state}.")
    lines.extend(["", "| Tool | Version | Command | Result |", "| --- | --- | --- | --- |"])
    results = list(load_results(directory))
    for result in results:
        lines.append(markdown_result(result))
    for result in results:
        if result.findings:
            lines.extend(["", f"## {markdown_text(result.tool)}", ""])
            lines.extend(f"- {markdown_text(finding)}" for finding in result.findings)
    return "\n".join(lines)


def scorecard(directory, *, open_findings=None, package_vulnerabilities=None, rejected_requests=None):
    statuses = [result.status for result in load_results(directory)]
    rows = [
        ("Passed checks", statuses.count("pass")),
        ("Failed checks", statuses.count("fail")),
        ("Checks not run", statuses.count("not_run")),
        ("Inapplicable checks", statuses.count("not_applicable")),
        ("Open findings", open_findings),
        ("Dependency vulnerabilities", package_vulnerabilities),
        ("Rejected requests", rejected_requests),
    ]
    lines = ["# Security scorecard", "", "| Metric | Count |", "| --- | --- |"]
    for name, count in rows:
        value = "Not measured" if count is None else count
        lines.append(f"| {name} | {value} |")
    return "\n".join(lines)


def nonnegative_count(value):
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError("Expected a nonnegative count.")
    return count


def run(tool, version, command, *, input_data=None, timeout=None):
    print(f"Running {tool}: {shlex.join(command)}", flush=True)
    try:
        code = subprocess.run(command, cwd=ROOT, check=False, input=input_data, timeout=timeout).returncode
    except (OSError, subprocess.TimeoutExpired) as error:
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
        entries = json.loads((ROOT / SECURITY / "bandit-exceptions.json").read_text(), object_pairs_hook=unique_json_object)
        today = datetime.now(timezone.utc).date()
        if any(not valid_exception(item, today) for item in entries):
            raise ValueError("Invalid or expired Bandit exception.")
        signatures = {
            (item["rule"], item["file"], item["code"], item["statementSha256"]): item.get("occurrences", 1)
            for item in entries
        }
        keys = signatures.keys()
        if len(keys) != len(entries) or any(
            not code or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or type(count) is not int or count < 1
            for (_, _, code, digest), count in signatures.items()
        ):
            raise ValueError("Invalid or duplicate Bandit exception signature.")
        files = [path for path in git("ls-files", "-z", "--", "backend").split("\0")
                 if path.endswith(".py") and not path.startswith(
                     ("backend/dev/security/fixtures/", f"{FIXTURES}/"))
                 and (ROOT / path).is_file() and not (ROOT / path).is_symlink()]
        if not files:
            raise ValueError("No tracked Python files to scan.")
        sources = {}
        grouped = {}
        for item in bandit_findings(command, files):
            filename = Path(item["filename"]).as_posix()
            if filename not in files:
                raise ValueError("Bandit reported a file outside the tracked scan.")
            if filename not in sources:
                source = (ROOT / filename).read_text()
                sources[filename] = source, ast.parse(source, filename=filename)
            line = item["line_number"]
            key = (item["test_id"], filename, *bandit_source_signature(*sources[filename], line))
            grouped.setdefault(key, []).append(line)
        matched = {
            key for key, lines in grouped.items()
            if len(lines) == signatures.get(key)
        }
        unreviewed = tuple(
            f"{rule} · {filename}:{line}"
            for rule, filename, code, digest in sorted(grouped.keys() - matched)
            for line in sorted(grouped[(rule, filename, code, digest)])
        )
        unused = tuple(
            f"Unused exception · {rule} · {filename} · {code} · {digest}"
            for rule, filename, code, digest in sorted(keys - matched)
        )
        for finding in (*unreviewed, *unused):
            print(f"Bandit: {finding}")
        return replace(result, status="fail" if unreviewed or unused else "pass",
                       findings=(*unreviewed, *unused))
    except (OSError, SyntaxError, TypeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Bandit check failed: {error}")
        return result


def bandit_source_signature(source, tree, line):
    statements = [node for node in ast.walk(tree) if isinstance(node, ast.stmt)
                  and node.lineno <= line <= node.end_lineno]
    if not statements:
        raise ValueError("Bandit finding has no matching Python statement.")
    statement = max(statements, key=lambda node: (node.lineno, node.col_offset, -node.end_lineno))
    parents = sorted(
        (node for node in statements if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))),
        key=lambda node: (node.lineno, node.col_offset),
    )
    scope = ".".join(node.name for node in parents)
    code = source.splitlines()[line - 1].strip()
    content = ast.get_source_segment(source, statement)
    return code, hashlib.sha256(f"{scope}\n{content}".encode()).hexdigest()


def dependency_locks(files):
    return [path for path in files if not path.startswith(f"{FIXTURES}/")
            and Path(path).name in {"requirements.txt", "package-lock.json", "uv.lock",
                                    "poetry.lock", "Pipfile.lock", "pnpm-lock.yaml", "yarn.lock"}]


def python_manifests():
    return sorted(path for path in git("ls-files", "-z").split("\0")
                  if path.startswith("backend/") and Path(path).name == "pyproject.toml")


def manifest_digest(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode() + b"\0" + (ROOT / path).read_bytes() + b"\0")
    return digest.hexdigest()


def generated_lock():
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
    return header + output


def compile_lock():
    (ROOT / SECURITY / "requirements.txt").write_text(generated_lock())


def verify_python_lock(locks, *, reproduce=False):
    lock = SECURITY / "requirements.txt"
    if str(lock) not in locks:
        raise ValueError("Tracked backend Python dependency lock is missing.")
    expected = f"# Manifest SHA256: {manifest_digest(python_manifests())}"
    content = (ROOT / lock).read_text()
    if expected not in content.splitlines():
        raise ValueError("Python dependency lock is stale. Run backend/dev/security/compile-lock.")
    if reproduce and generated_lock() != content:
        raise ValueError("Python lock differs from the generated lock.")


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


def scan_dependencies(requirements=None, *, reproduce=False):
    command = ["osv-scanner", "scan", "source", "--offline", "--format", "json",
               "--config", str(OSV_CONFIG)]
    locks = dependency_locks(git("ls-files", "-z").split("\0"))
    result = Result("OSV-Scanner", OSV, shlex.join(command) + " LOCKFILES", "fail")
    try:
        try:
            output = subprocess.check_output(["osv-scanner", "--version"], text=True, cwd=ROOT)
        except FileNotFoundError:
            print("OSV-Scanner is not available on PATH.")
            return replace(result, status="not_run")
        if not locks:
            raise ValueError("No tracked dependency lock files.")
        verify_python_lock(locks, reproduce=reproduce)
        if requirements is not None:
            locks.append(str(requirements))
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
        unchecked = []
        for lock in locks:
            path = Path(lock)
            if path.suffix != ".txt":
                continue
            label = path.name if path.is_absolute() else path
            names = re.findall(r"(?mi)^[ 	]*([a-z0-9][a-z0-9_.-]*)[ 	]*@[ 	]*git\+",
                               (ROOT / path).read_text())
            unchecked.extend(f"not_run · {label} · {name} · Git dependency outside offline OSV scan"
                             for name in sorted(set(names)))
        notes = (*sorted(findings), *unchecked)
        for note in notes:
            print(f"OSV: {note}")
        return replace(result, status="fail" if findings else "pass", findings=notes)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"OSV check failed: {error}")
        return result


def exit_status(results, *, ci, must_run=()):
    return int(any(result.status == "fail"
                   or (result.status == "not_run" and (result.tool in must_run or (ci and result.required)))
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


def contract_command(contract, port, config, report, *, writes=False):
    command = ["uvx", "--python", "3.12", "--exclude-newer", VERSIONS["TOOL_CUTOFF"],
               f"schemathesis@{SCHEMATHESIS}", "--config-file", str(config), "run", str(contract),
               "--origin", f"http://127.0.0.1:{port}", "--checks", CONTRACT_CHECKS,
               "--mode", "positive", "--phases", "examples,coverage,fuzzing", "--max-examples", "20",
               "--generation-deterministic", "--workers", "1", "--max-redirects", "0",
               "--request-timeout", "10", "--no-color", "--report", "json", "--report-json-path", str(report)]
    if not writes:
        command[command.index("--checks"):command.index("--checks")] = ["--include-method", "GET"]
    return command


def contract_findings(report, contract):
    if report.get("complete") is not True or report.get("errors"):
        raise ValueError(f"Schemathesis did not complete {contract}.")
    return tuple(f"{contract} · {failure['code']} {failure['title']} · {operation}"
                 for failure in report["failures"] for operation in failure["operations"])


def contract_session(host, port):
    user = os.environ.get("FS_API_TEST_USER")
    password = os.environ.get("FS_API_TEST_PASSWORD")
    if not user and not password:
        return None
    if not user or not password or user.lower() in ("administrator", "guest"):
        raise ValueError("Use only the fabricated development test user for contract checks.")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("POST", "/api/method/login", urlencode({"usr": user, "pwd": password}),
                           {"Host": f"{host}:{port}", "Content-Type": "application/x-www-form-urlencoded"})
        with connection.getresponse() as response:
            response.read()
            cookies = [value for name, value in response.getheaders() if name.lower() == "set-cookie"]
            if response.status != 200:
                raise ValueError(f"Test user sign-in returned HTTP {response.status}.")
    finally:
        connection.close()
    sid = next((cookie.split(";", 1)[0][4:] for cookie in cookies if cookie.startswith("sid=")), "")
    if not sid or sid == "Guest":
        raise ValueError("Test user sign-in returned no session.")
    return sid


class ContractToolError(ValueError):
    pass


def run_contract(contract, host, port, *, writes=False, sid=None):
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "schemathesis.toml"
        headers = {"Host": f"{host}:{port}"}
        if sid:
            headers["Cookie"] = "sid=${FS_SCHEMATHESIS_SID}"
        config.write_text("headers = { " + ", ".join(f"{json.dumps(name)} = {json.dumps(value)}"
                                                     for name, value in headers.items()) + " }\n")
        report_path = Path(directory) / "report.json"
        command = contract_command(ROOT / contract, port, config, report_path, writes=writes)
        environment = {name: value for name, value in os.environ.items()
                       if name not in ("FS_API_TEST_USER", "FS_API_TEST_PASSWORD")}
        environment["FS_SCHEMATHESIS_SID"] = sid or ""
        print(f"Running Schemathesis: {contract}", flush=True)
        # The tool keeps a crash cache in its working directory; keep it out of the repository.
        try:
            process = subprocess.run(command, cwd=directory, check=False, env=environment, timeout=600,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            raise ContractToolError(f"CONTRACT_TOOL_FAILED {contract}") from None
        try:
            report = json.loads(report_path.read_text())
        except (OSError, ValueError):
            raise ContractToolError(f"CONTRACT_REPORT_UNAVAILABLE {contract}") from None
        if process.returncode == 2 and report.get("operations", {}).get("selected") == 0:
            print(f"Schemathesis: {contract} has no operations for this mode.")
            return (), 0
        findings = contract_findings(report, contract)
        if process.returncode not in (0, 1) or (process.returncode == 1) != bool(findings):
            raise ContractToolError(f"CONTRACT_STATUS_UNEXPECTED {contract}")
        return findings, report["operations"]["tested"]


class ContractFixture(BaseHTTPRequestHandler):
    """Answer the fixture contract with a server error."""

    def do_GET(self):
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args):
        pass


def contract_fixture_found():
    with HTTPServer(("127.0.0.1", 0), ContractFixture) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            findings, _tested = run_contract(str(CONTRACT_FIXTURE), "fixture.localhost",
                                             server.server_port)
        finally:
            server.shutdown()
            thread.join()
    return any(" ST101 " in finding and "GET /api/method/fixture.read" in finding for finding in findings)


def scan_contracts(target, *, writes=False, contracts=None):
    mode = "--allow-writes" if writes else "GET only"
    result = Result("Schemathesis API contract", SCHEMATHESIS,
                    f"backend/dev/bin/security-full --api-target LOCAL_URL ({mode})", "fail")
    if target is None:
        print("Schemathesis: no local API target. Use --api-target or FS_API_TARGET.")
        return replace(result, status="not_run")
    host, port = local_target(target)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/api/method/ping", headers={"Host": f"{host}:{port}"})
        with connection.getresponse() as response:
            response.read()
    except ConnectionRefusedError:
        print("Schemathesis: local site is not listening.")
        return replace(result, status="not_run")
    except (OSError, http.client.HTTPException) as error:
        print(f"Schemathesis: local site check failed: {error}")
        return result
    finally:
        connection.close()
    try:
        sid = contract_session(host, port)
        if contracts is None:
            contracts = [path for path in git("ls-files", "-z", "--", str(CONTRACTS)).split("\0")
                         if path.endswith((".yaml", ".yml", ".json"))]
        if not contracts:
            raise ValueError("No tracked API contracts.")
        if not contract_fixture_found():
            raise ValueError("Schemathesis missed its fixture.")
        runs = [run_contract(contract, host, port, writes=writes, sid=sid) for contract in contracts]
        findings = tuple(finding for items, _tested in runs for finding in items)
        for finding in findings:
            print(f"Schemathesis: {finding}")
        tested = sum(count for _findings, count in runs)
        print(f"Schemathesis: {tested} operations tested ({mode}). Authorization requires separate role tests.")
        if not findings and not tested:
            print("Schemathesis: no operation was tested.")
            return replace(result, status="not_run")
        return replace(result, status="fail" if findings else "pass", findings=findings)
    except ContractToolError as error:
        print(error)
        return result
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Schemathesis check failed: {error}")
        return result


def default_api_target():
    if os.environ.get("FS_API_TARGET"):
        return os.environ["FS_API_TARGET"]
    port = os.environ.get("PANE_PORT", "")
    return f"http://kiraci1.localhost:{int(port) + 1}" if port.isdigit() else None


def scan_full(requirements, *, ci=False, runtime_image=None, api_target=None, allow_writes=False):
    if api_target is not None:
        local_target(api_target)
    source = source_state()
    save(RESULTS, "full", [], source)
    results = [
        run("Security tool tests", "Python", [sys.executable, "-B", "-m", "unittest", "discover",
                                               "-s", str(SECURITY)]),
        run("Backend gate", f"Semgrep {VERSIONS['SEMGREP_VERSION']} / Gitleaks {VERSIONS['GITLEAKS_VERSION']}",
            ["backend/dev/bin/security-audit"]),
        scan_bandit(),
        run("Gitleaks", VERSIONS["GITLEAKS_VERSION"], [str(SECURITY / "history-scan")]),
        scan_dependencies(requirements, reproduce=ci),
        runtime_inventory(runtime_image),
        scan_contracts(api_target, writes=allow_writes),
    ]
    save(RESULTS, "full", results, source)
    return exit_status(results, ci=ci, must_run=("OSV-Scanner",))


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


def scan_zap(url, status, reason, headers, body):
    profile = os.environ.get("FS_COLIMA_PROFILE", "factory")
    contexts = {"factory": ["--context", "colima-factory"], "default": ["--context", "colima"], "ci": []}
    version = VERSIONS["ZAP_VERSION"]
    if profile not in contexts:
        print("FS_COLIMA_PROFILE must be factory, default or ci.")
        return Result("ZAP passive scan", version, "docker run", "fail")

    image = f"ghcr.io/zaproxy/zaproxy:{version}@{VERSIONS['ZAP_DIGEST']}"
    mime = next((value for name, value in headers if name.lower() == "content-type"), "application/octet-stream")
    har = {"log": {"version": "1.2", "creator": {"name": "dast-scan", "version": "1"},
                   "entries": [{
                       "startedDateTime": datetime.now(timezone.utc).isoformat(),
                       "time": 0,
                       "request": {"method": "GET", "url": url, "httpVersion": "HTTP/1.1",
                                   "headers": [{"name": "Host", "value": urlsplit(url).netloc}],
                                   "cookies": [], "queryString": [], "headersSize": -1, "bodySize": 0},
                       "response": {"status": status, "statusText": reason, "httpVersion": "HTTP/1.1",
                                    "headers": [{"name": name, "value": value} for name, value in headers],
                                    "cookies": [], "headersSize": -1, "bodySize": len(body),
                                    "content": {"size": len(body), "mimeType": mime, "encoding": "base64",
                                                "text": base64.b64encode(body).decode("ascii")}},
                       "cache": {}, "timings": {"send": 0, "wait": 0, "receive": 0},
                   }]}}
    plan = {"env": {"contexts": [{"name": "local", "urls": [url]}],
                    "parameters": {"failOnError": True}},
            "jobs": [
                {"type": "import", "parameters": {"type": "har", "fileName": "/tmp/scan/response.har",
                                                  "sendRequests": False}},
                {"type": "passiveScan-wait", "parameters": {"maxDuration": 2}},
                {"type": "report", "parameters": {"template": "traditional-json", "reportDir": "/tmp/scan",
                                                  "reportFile": "report.json"}},
                {"type": "exitStatus", "parameters": {"errorLevel": "Medium", "warnLevel": "Low"}},
            ]}
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        for file, data in (("plan.yaml", plan), ("response.har", har)):
            content = json.dumps(data).encode()
            item = tarfile.TarInfo(file)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    command = ["docker", *contexts[profile], "run", "--rm", "-i", "--pull", "never", "--network", "none",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", image,
               "-ec", "mkdir -p /tmp/scan; tar -xf - -C /tmp/scan; "
                      "status=0; /zap/zap.sh -cmd -silent -dir /tmp/zap -autorun /tmp/scan/plan.yaml "
                      ">/tmp/scan/zap.log 2>&1 || status=$?; "
                      "cat /tmp/scan/report.json || exit 3; exit \"$status\""]
    result = Result("ZAP passive scan", version, shlex.join(command), "fail")
    try:
        process = subprocess.run(command, cwd=ROOT, check=False, input=payload.getvalue(),
                                 capture_output=True, timeout=180)
        findings = zap_findings(json.loads(process.stdout), url)
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError):
        print("ZAP_REPORT_UNAVAILABLE")
        return result
    for finding in findings:
        print(f"ZAP: {finding}")
    return replace(result, status="pass" if process.returncode == 0 else "fail", findings=findings)


def zap_findings(report, url):
    risks = {"0": "Informational", "1": "Low", "2": "Medium", "3": "High"}
    target = urlsplit(url)
    findings = set()
    for site in report["site"]:
        for alert in site["alerts"]:
            alert_id = str(alert.get("alertRef") or alert["pluginid"])
            if not re.fullmatch(r"[0-9]+(?:-[0-9]+)*", alert_id):
                raise ValueError("Invalid ZAP alert ID.")
            risk = risks[str(alert["riskcode"])]
            for instance in alert["instances"]:
                address = urlsplit(instance["uri"])
                if (address.scheme == target.scheme and address.hostname == target.hostname
                        and (address.port if address.port is not None else 80) == (target.port or 80)
                        and (address.path or "/") == (target.path or "/")
                        and not (address.query or address.fragment or address.username is not None)):
                    findings.add(f"{alert_id} · {risk} · {url}")
    return tuple(sorted(findings))


def scan_local(target, *, ci=False):
    host, port = local_target(target)
    source = source_state()
    save(RESULTS, "local", [], source)
    zap = Result("ZAP passive scan", VERSIONS["ZAP_VERSION"], "docker run", "not_run")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/", headers={"Host": f"{host}:{port}"})
        with connection.getresponse() as response:
            print(f"HTTP {response.status}")
            body = response.read(1024 * 1024 + 1)
            if len(body) <= 1024 * 1024:
                zap = scan_zap(f"http://{host}:{port}/", response.status, response.reason,
                               response.getheaders(), body)
            else:
                print("Response exceeds the passive scan limit of 1 MiB.")
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
               zap]
    save(RESULTS, "local", results, source)
    return exit_status(results, ci=ci)


def main():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="mode", required=True)
    full = subcommands.add_parser("full")
    full.add_argument("--requirements", type=lambda value: Path(value).resolve())
    full.add_argument("--runtime-image")
    full.add_argument("--api-target", default=default_api_target())
    full.add_argument("--allow-writes", action="store_true",
                      help="Also send generated POST, PUT, PATCH and DELETE requests to the local site.")
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
        try:
            return scan_full(args.requirements, ci=args.ci, runtime_image=args.runtime_image,
                             api_target=args.api_target, allow_writes=args.allow_writes)
        except ValueError as error:
            parser.error(str(error))
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


def markdown_text(value):
    line = " ".join(str(value).splitlines())
    return re.sub(r"[&<>\\`*_{}\[\]|~!#+$-]", lambda match: f"&#{ord(match[0])};", line)


def markdown_code(value):
    line = " ".join(str(value).splitlines()) or "—"
    if "|" in line:
        return markdown_text(line)
    ticks = re.findall(r"`+", line)
    if not ticks:
        return f"`{line}`"
    fence = "`" * (max(map(len, ticks)) + 1)
    return f"{fence} {line} {fence}"


def markdown_result(result):
    fields = (markdown_text(result.tool), markdown_text(result.version),
              markdown_code(result.command), markdown_code(result.status))
    return "| " + " | ".join(fields) + " |"


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in Bandit exception JSON.")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
