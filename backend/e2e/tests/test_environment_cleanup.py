"""Check environment cleanup without contacting Docker or Colima."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ENVIRONMENT = Path(__file__).resolve().parents[1] / "environment.sh"
PROJECT = "fs-integration-e2e-43820"
IMAGE = "fs-tenant-dev:43820"


class EnvironmentCleanupTest(unittest.TestCase):
    def setUp(self):
        sandbox = tempfile.TemporaryDirectory(dir=os.environ.get("PANE_SCRATCH_DIR"))
        self.addCleanup(sandbox.cleanup)
        root = Path(sandbox.name)
        (root / "e2e").mkdir()
        self.script = root / "e2e" / ENVIRONMENT.name
        shutil.copyfile(ENVIRONMENT, self.script)
        (root / "dev/bin").mkdir(parents=True)
        (root / "dev/.env").touch()
        self.log = root / "calls.log"
        self.environment = {
            **os.environ,
            "DEV_ENV_FILE": str(root / "dev/.env"),
            "PANE_PORT": "43820",
            "PATH": f"{root / 'dev/bin'}:{os.environ['PATH']}",
            "CALLS": str(self.log),
        }
        tunnel = root / "dev/bin/tunnel"
        tunnel.write_text('#!/bin/bash\nprintf "tunnel %s\\n" "$*" >> "$CALLS"\n')
        tunnel.chmod(0o700)
        docker = root / "dev/bin/docker"
        docker.write_text(
            '#!/bin/bash\n'
            'printf "%s\\n" "$*" >> "$CALLS"\n'
            'case "$3:$4" in\n'
            '  container:inspect) exit 1 ;;\n'
            '  image:ls)\n'
            '    if [[ "$IMAGE_OWNER" == fs-integration-e2e-43820 ]]; then\n'
            '      printf "image-id\\n"\n'
            '    fi ;;\n'
            '  image:rm) exit "${REMOVE_STATUS:-0}" ;;\n'
            'esac\n'
        )
        docker.chmod(0o700)

    def down(self, profile, owner, *, remove_status=0):
        result = subprocess.run(
            ["/bin/bash", str(self.script), "down"],
            env={
                **self.environment,
                "FS_COLIMA_PROFILE": profile,
                "IMAGE_OWNER": owner,
                "REMOVE_STATUS": str(remove_status),
            },
            capture_output=True,
            text=True,
        )
        return result, self.log.read_text().splitlines()

    def test_default_cleanup_removes_only_its_tag_after_compose_down(self):
        result, calls = self.down("default", PROJECT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            f"--context colima image ls --filter reference={IMAGE} "
            f"--filter label=com.docker.compose.project={PROJECT} --format {{{{.ID}}}}",
            calls,
        )
        self.assertEqual(calls[-1], f"--context colima image rm --no-prune {IMAGE}")
        self.assertTrue(any(call.endswith("down --volumes") for call in calls[:-1]))

    def test_default_cleanup_leaves_missing_or_foreign_tag_alone(self):
        for owner in ("", "fs-dev-ortam-43820"):
            with self.subTest(owner=owner):
                result, calls = self.down("default", owner)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(any(" image rm " in call for call in calls))

    def test_factory_cleanup_leaves_image_and_volumes_alone(self):
        result, calls = self.down("factory", PROJECT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(" image " in call or "down --volumes" in call for call in calls))

    def test_cleanup_reports_image_removal_failure_after_closing_tunnel(self):
        result, calls = self.down("default", PROJECT, remove_status=1)
        self.assertEqual(result.returncode, 1)
        self.assertIn("tunnel kapat", calls)


if __name__ == "__main__":
    unittest.main()
