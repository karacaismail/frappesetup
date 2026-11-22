"""Exercise the advisory ShellCheck step through the readiness command."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).with_name("gate.py").resolve()
SCRATCH = GATE.parents[3] / ".pane" / "scratch"


class ShellCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet", self.repository], check=True)
        self.root = self.repository / "backend"
        (self.root / "apps").mkdir(parents=True)
        self.tools = self.repository / "tools"
        self.tools.mkdir()
        self.write(
            "AGENTS.md",
            (
                "## Klasörler ve sahipleri\n\n"
                "| Klasör | İçerik | Sahip iş |\n"
                "| --- | --- | --- |\n"
                "| `dev/` | Betikler | second-owner |\n"
                "| `e2e/` | Deneme | first-owner |\n"
            ),
        )
        self.write("dev/bin/run", "#!/usr/bin/env bash\necho $1\n")
        self.write("e2e/check.sh", "#!/bin/sh\necho $1\n")
        self.write("dev/bin/python-tool", "#!/usr/bin/env python3\nprint('hi')\n")

    def write(self, relative, content):
        file = self.root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    def fake_docker(self, body):
        docker = self.tools / "docker"
        docker.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        docker.chmod(0o755)

    def scan(self, *args):
        return subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, *args],
            env=dict(
                os.environ, PATH=f"{self.tools}{os.pathsep}{os.environ['PATH']}", FS_COLIMA_PROFILE="factory"
            ),
            capture_output=True,
            text=True,
        )

    def test_shellcheck_findings_are_nonblocking_and_grouped_by_owner(self):
        self.fake_docker(
            """
import json, sys, tarfile
args = sys.argv[1:]
assert args[:3] == ['--context', 'colima-factory', 'run']
assert '--pull' in args and args[args.index('--pull') + 1] == 'never'
assert '--network' in args and args[args.index('--network') + 1] == 'none'
assert any(arg.startswith('koalaman/shellcheck-alpine:v0.11.0@sha256:') for arg in args)
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
    entries = {item.name for item in archive}
assert entries == {'backend/dev/bin/run', 'backend/e2e/check.sh'}
print(json.dumps({'comments': [
    {'file': 'backend/dev/bin/run', 'line': 2, 'code': 2086, 'message': 'Quote variable.', 'level': 'info'},
    {'file': 'backend/e2e/check.sh', 'line': 2, 'code': 2086, 'message': 'Quote variable.', 'level': 'info'},
]}))
raise SystemExit(1)
"""
        )
        result = self.scan("--json")
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["shellcheck"], "warn")
        self.assertEqual(
            [(row["owner"], row["path"], row["severity"], row["rule"]) for row in payload["findings"]],
            [
                ("first-owner", "e2e/check.sh", "warning", "shellcheck.SC2086"),
                ("second-owner", "dev/bin/run", "warning", "shellcheck.SC2086"),
            ],
        )
        human = self.scan()
        self.assertLess(human.stdout.index("first-owner"), human.stdout.index("second-owner"))
        self.write("docs/decisions/0001-first.md", "# First")
        self.write("docs/decisions/0001-second.md", "# Second")
        self.assertEqual(self.scan("--json").returncode, 1)

    def test_unavailable_image_is_not_run(self):
        self.fake_docker("raise SystemExit(125)\n")
        result = self.scan("--json")
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["shellcheck"], "not_run")
        self.assertEqual(payload["findings"], [])
        self.assertIn("shellcheck: not_run", self.scan().stderr)

    def test_clean_and_malformed_output_have_different_status(self):
        for output, expected in (('{"comments": []}', "pass"), ("invalid Docker output", "not_run")):
            with self.subTest(output=output):
                self.fake_docker(f"print({output!r})\n")
                result = self.scan("--json")
                self.assertEqual(result.returncode, 0, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["checks"]["shellcheck"], expected)
                self.assertEqual(payload["findings"], [])
