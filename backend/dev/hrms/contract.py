#!/usr/bin/env python3
"""Run the HRMS TR Schemathesis contract check as the test employee and as a guest.

The HRMS TR stack keeps its network internal, so the site has no host port.
This script opens a loopback relay on the host. Each relay connection runs
``compose exec -T web`` and copies bytes to the site's own port in the container.
The employee signs in through Frappe's standard login endpoint, like any user.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = "backend/contracts/hrms_tr.openapi.yaml"
COMPOSE = Path(__file__).with_name("compose")
RELAY = (
    "import os, socket, sys, threading\n"
    "s = socket.create_connection(('127.0.0.1', int(os.environ['FS_TENANT_WEB_PORT'])))\n"
    "def up():\n"
    "    while True:\n"
    "        b = os.read(0, 65536)\n"
    "        if not b:\n"
    "            break\n"
    "        s.sendall(b)\n"
    "    s.shutdown(socket.SHUT_WR)\n"
    "threading.Thread(target=up, daemon=True).start()\n"
    "while True:\n"
    "    b = s.recv(65536)\n"
    "    if not b:\n"
    "        break\n"
    "    os.write(1, b)\n"
)


def compose(prefix, *args, **kwargs):
    return subprocess.run([*prefix, *args], check=True, text=True, capture_output=True, **kwargs).stdout


def pipe(source, write, close):
    try:
        while True:
            chunk = source(65536)
            if not chunk:
                break
            write(chunk)
    except OSError:
        pass
    finally:
        close()


class Relay:
    """Accept loopback connections and forward each one into the web container."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.close()

    def serve(self):
        while True:
            try:
                connection, _address = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self.forward, args=(connection,), daemon=True).start()

    def forward(self, connection):
        process = subprocess.Popen(
            [*self.prefix, "exec", "-T", "web", "env/bin/python", "-u", "-c", RELAY],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        upstream = threading.Thread(
            target=pipe, args=(connection.recv, process.stdin.write, process.stdin.close), daemon=True
        )
        upstream.start()
        pipe(process.stdout.read, connection.sendall, lambda: None)
        connection.close()
        process.stdout.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def employee_credentials(prefix, manifest):
    data = json.loads(compose(prefix, "exec", "-T", "web", "cat", manifest))
    password = compose(prefix, "exec", "-T", "web", "printenv", "HRT_TEST_PASSWORD").strip()
    if not password:
        raise ValueError("The web container has no HRT_TEST_PASSWORD.")
    return data["users"]["employee"], password


def run(site, prefix, manifest, modes):
    sys.path.insert(0, str(ROOT / "backend/dev/security"))
    os.chdir(ROOT)
    from scans import contract_session, run_contract

    failed = False
    with Relay(prefix) as relay:
        for mode in modes:
            sid = None
            if mode == "employee":
                user, password = employee_credentials(prefix, manifest)
                os.environ["FS_API_TEST_USER"], os.environ["FS_API_TEST_PASSWORD"] = user, password
                try:
                    sid = contract_session(site, relay.port)
                finally:
                    os.environ.pop("FS_API_TEST_USER")
                    os.environ.pop("FS_API_TEST_PASSWORD")
                print("HRMS TR employee session opened.", flush=True)
            findings, tested = run_contract(CONTRACT, site, relay.port, sid=sid)
            print(f"{mode}: {tested} operations tested. {len(findings)} findings.", flush=True)
            for finding in findings:
                print(f"{mode}: {finding}", flush=True)
            failed = failed or bool(findings) or not tested
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True, help="Test site name, for example test-hrms-tr.localhost.")
    parser.add_argument(
        "--compose",
        default=str(COMPOSE),
        help="Compose wrapper for this stack. The default is backend/dev/hrms/compose.",
    )
    parser.add_argument(
        "--manifest",
        default="/tmp/hrms_tr-manifest.json",
        help="Seed manifest path inside the web container.",
    )
    parser.add_argument("--mode", choices=("employee", "guest", "both"), default="both")
    args = parser.parse_args(argv)
    modes = ("employee", "guest") if args.mode == "both" else (args.mode,)
    try:
        return run(args.site, [args.compose], args.manifest, modes)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"HRMS TR contract check failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
