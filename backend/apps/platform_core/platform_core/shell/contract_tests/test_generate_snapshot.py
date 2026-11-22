"""Verify the canonical shell schema snapshot can be reproduced."""

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve()
GENERATOR = SCRIPT.with_name("generate_snapshot.py")
CONTRACT = SCRIPT.parents[5] / "contracts" / "platform_core-shell.openapi.yaml"


class TestSnapshotGenerator(unittest.TestCase):
	def test_tracked_snapshot_matches_generator(self):
		if not CONTRACT.is_file():
			self.skipTest("The generation check needs the canonical source in a repository checkout.")
		result = subprocess.run(
			[sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True, check=False
		)
		self.assertEqual(result.returncode, 0, result.stderr)
