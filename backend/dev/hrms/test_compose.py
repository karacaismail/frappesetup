"""Check profile routing without contacting Docker or starting a site."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

COMPOSE = Path(__file__).with_name("compose")


class MeasurementImageTest(unittest.TestCase):
    def test_measurement_script_is_included_in_build_context(self):
        dockerignore = Path(__file__).with_name("Dockerfile.dockerignore")
        self.assertIn("!dev/hrms/measure.py", dockerignore.read_text(encoding="utf-8").splitlines())


class ComposeProfileTest(unittest.TestCase):
    def run_compose(self, profile=None):
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
            docker.chmod(0o700)
            env = {**os.environ, "PATH": f"{directory}:{os.environ['PATH']}", "PANE_PORT": "3850"}
            env.pop("FS_COLIMA_PROFILE", None)
            if profile is not None:
                env["FS_COLIMA_PROFILE"] = profile
            return subprocess.run(
                [str(COMPOSE), "config", "--quiet"], env=env, capture_output=True, text=True, check=False
            )

    def test_factory_context_is_default(self):
        result = self.run_compose()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[:3], ["--context", "colima-factory", "compose"])

    def test_default_profile_uses_colima_context(self):
        result = self.run_compose("default")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[:3], ["--context", "colima", "compose"])

    def test_unknown_profile_is_rejected_before_docker(self):
        result = self.run_compose("unknown")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("FS_COLIMA_PROFILE", result.stderr)
