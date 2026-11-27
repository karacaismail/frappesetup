"""Check that CI runs every backend gate and that the required check waits for them."""

import os
from pathlib import Path
import re
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"

# Each backend gate: job name -> commands that must appear as whole `run` steps.
GATES = {
    "backend-shared-files": ("python3.14 -B backend/dev/check_shared_files.py",),
    "backend-module-boundaries": ("backend/dev/bin/module-boundaries",),
    "backend-security": ("backend/dev/bin/security-audit",),
    "backend-ai-readiness": ("backend/dev/bin/ai-readiness",),
    "backend-tests": (
        "python3.14 -B -m unittest discover -s backend/dev/tests",
        "python3.14 -B -m unittest discover -s backend/dev/naming/tests",
        "python3 -I -m unittest discover -s backend/deploy/tests -v",
        "python3.14 -B -m unittest discover -s .github/tests",
    ),
    "press-ai": (
        "python3 -I -m unittest discover -s packages/press-ai/tests",
        "python3 -I packages/press-ai/server.py check-contract",
    ),
}


def run_lines(step):
    return [line.strip() for line in step.get("run", "").splitlines() if line.strip()]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    def test_every_gate_runs_unconditionally(self):
        for job_name, commands in GATES.items():
            with self.subTest(job=job_name):
                job = self.jobs[job_name]
                self.assertNotIn("if", job)
                self.assertFalse(job.get("continue-on-error"))
                lines = {}
                for step in job["steps"]:
                    for line in run_lines(step):
                        lines[line] = step
                for command in commands:
                    self.assertIn(command, lines)
                    step = lines[command]
                    self.assertNotIn("if", step)
                    self.assertFalse(step.get("continue-on-error"))

    def test_module_boundaries_use_python_3_14(self):
        steps = self.jobs["backend-module-boundaries"]["steps"]
        setup = [s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python@")]
        self.assertEqual(len(setup), 1)
        self.assertTrue(str(setup[0]["with"]["python-version"]).startswith("3.14"))

    def test_required_check_waits_for_every_gate(self):
        aggregate = self.jobs["build-and-test"]
        for job_name in (*GATES, "build", "e2e"):
            self.assertIn(job_name, aggregate["needs"])
        self.assertEqual(aggregate["if"], "${{ always() }}")

    def test_required_check_rejects_any_unsuccessful_job(self):
        aggregate = self.jobs["build-and-test"]
        step = next(s for s in aggregate["steps"] if "RESULTS" in s.get("env", {}))
        self.assertEqual(step["env"]["RESULTS"], "${{ join(needs.*.result, ' ') }}")
        others = ["success"] * (len(aggregate["needs"]) - 1)
        for result in ("success", "failure", "cancelled", "skipped"):
            for position in (0, len(others)):
                with self.subTest(result=result, position=position):
                    results = list(others)
                    results.insert(position, result)
                    process = subprocess.run(
                        ["bash", "-e", "-c", step["run"]],
                        env={**os.environ, "RESULTS": " ".join(results)},
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(process.returncode, 0 if result == "success" else 1)

    def test_external_actions_use_full_commit_hashes(self):
        for job in self.jobs.values():
            for step in job["steps"]:
                action = step.get("uses", "./")
                if not action.startswith("./"):
                    self.assertIsNotNone(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action)


if __name__ == "__main__":
    unittest.main()
