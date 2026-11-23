import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from press_core_guard import compare, snapshot


class PressCoreGuardTest(unittest.TestCase):
	def setUp(self):
		directory = tempfile.TemporaryDirectory()
		self.addCleanup(directory.cleanup)
		self.core = Path(directory.name)
		self.controller = self.core / "controller.py"
		self.controller.write_text("original")
		self.before = snapshot(self.core)

	def test_read_only_extension_passes(self):
		self.assertEqual(self.controller.read_text(), "original")
		self.assertEqual(compare(self.before, snapshot(self.core)), 0)

	def test_extension_that_writes_core_fails(self):
		self.controller.write_text("modified")
		output = io.StringIO()
		with redirect_stderr(output):
			status = compare(self.before, snapshot(self.core))
		self.assertEqual(status, 1)
		self.assertIn("Press core changed: controller.py", output.getvalue())
