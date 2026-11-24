"""Tests for the CI browser install script (.github/actions/playwright-browsers/install.sh).

AJA-382: a network attempt hit its time limit, but the inner `apt-get` kept running
and held the dpkg lock; the next attempts failed at once. These tests run the script's
network loop with a fake slow `npx`. The fake starts an `apt-get` child in its own
session, like `sudo` with a pty does, so killing the attempt's process group alone
does not reach it.

Run from the repository root:
    python3 -I -m unittest discover -s backend/deploy/tests
"""

import os
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github" / "actions" / "playwright-browsers" / "install.sh"
PYTHON = shutil.which("python3")

FAKE_NPX = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    # Fake `npx playwright install-deps`: the 1st call hangs, later calls succeed.
    set -u
    n=$(($(cat "$WORK/calls" 2>/dev/null || echo 0) + 1))
    echo "$n" > "$WORK/calls"
    if [ "$n" -gt 1 ]; then
      # Record whether the 1st attempt's processes were still alive at this point.
      for f in "$WORK"/pid.*; do
        if kill -0 "$(cat "$f")" 2>/dev/null; then echo alive; else echo dead; fi
      done > "$WORK/seen-by-retry"
      exit 0
    fi
    # Child in its own session named apt-get (escapes a process-group kill).
    "$PYTHON" -c 'import os, sys; os.setsid(); os.execv("/bin/sleep", ["apt-get", "300"])' \
      </dev/null >/dev/null 2>&1 &
    echo $! > "$WORK/pid.apt"
    # Plain child in the attempt's process group.
    sleep 300 </dev/null >/dev/null 2>&1 &
    echo $! > "$WORK/pid.group"
    wait
    """
)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class NetworkAttemptTimeout(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="pw-install-"))
        self.addCleanup(self.cleanup)
        bindir = self.work / "bin"
        bindir.mkdir()
        npx = bindir / "npx"
        npx.write_text(FAKE_NPX)
        npx.chmod(0o755)
        self.bindir = bindir

    def cleanup(self):
        for f in self.work.glob("pid.*"):
            try:
                os.kill(int(f.read_text()), 9)
            except (ProcessLookupError, ValueError):
                pass
        shutil.rmtree(self.work, ignore_errors=True)

    def run_loop(self, extra="", attempts=2, seconds=2, lock_wait=10):
        harness = textwrap.dedent(
            f"""\
            # sudo runs the command as the same user and logs it; dpkg is never run for real.
            sudo() {{
              echo "sudo $*" >> "$WORK/sudo.log"
              case "$1" in dpkg|tee) return 0 ;; esac
              "$@"
            }}
            source "{SCRIPT}"
            ARCHIVES="$WORK/archives"; DEBS="$WORK/debs"; MIRRORS="$WORK/no-mirrors"
            APT_LOCK_FILES="$WORK/no-lock"
            mkdir -p "$ARCHIVES"
            list_archives() {{ :; }}
            NET_ATTEMPTS={attempts}
            NET_ATTEMPT_SECONDS={seconds}
            {extra}
            before=$(mktemp)
            install_from_network "$before"
            """
        )
        env = {
            "PATH": f"{self.bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.work),
            "WORK": str(self.work),
            "PYTHON": PYTHON,
            "PW_APT_KILL_AFTER_SECONDS": "2",
            "PW_APT_LOCK_WAIT_SECONDS": str(lock_wait),
        }
        script = self.work / "harness.sh"
        script.write_text(harness)
        start = time.monotonic()
        proc = subprocess.run(
            ["bash", str(script)], env=env, capture_output=True, text=True, timeout=120
        )
        return proc, time.monotonic() - start

    def pids(self):
        return {f.name: int(f.read_text()) for f in self.work.glob("pid.*")}

    def test_timeout_stops_children_and_retry_waits_for_them(self):
        proc, elapsed = self.run_loop()
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual((self.work / "calls").read_text().strip(), "2", out)
        pids = self.pids()
        self.assertEqual(set(pids), {"pid.apt", "pid.group"}, out)
        # The retry started only after every process of the 1st attempt had stopped.
        self.assertEqual((self.work / "seen-by-retry").read_text().split(), ["dead", "dead"], out)
        for name, pid in pids.items():
            self.assertFalse(alive(pid), f"{name} ({pid}) still running\n{out}")
        log = (self.work / "sudo.log").read_text()
        self.assertIn("sudo dpkg --configure -a", log, out)
        self.assertLess(elapsed, 60, out)

    def test_lock_wait_has_its_own_limit(self):
        # The lock never comes free: the loop must give up instead of retrying.
        proc, elapsed = self.run_loop(extra="apt_busy() { return 0; }", lock_wait=2)
        out = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0, out)
        self.assertEqual((self.work / "calls").read_text().strip(), "1", out)
        self.assertLess(elapsed, 60, out)


if __name__ == "__main__":
    unittest.main()
