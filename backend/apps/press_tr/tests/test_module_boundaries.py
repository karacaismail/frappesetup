"""Protect the one-way dependency from HTTP routes to the identity module."""

import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "press_tr"


class ModuleBoundariesTest(unittest.TestCase):
	def test_identity_does_not_import_api_or_other_project_apps(self):
		identity_layer = APP / "press_identity"
		self.assertTrue(identity_layer.is_dir())
		for path in identity_layer.rglob("*.py"):
			for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
				if isinstance(node, ast.ImportFrom):
					names = [node.module or ""]
				elif isinstance(node, ast.Import):
					names = [alias.name for alias in node.names]
				else:
					continue
				for name in names:
					with self.subTest(path=path.name, module=name):
						self.assertNotIn(name.split(".")[0], {"platform_core", "identity_sync"})
						self.assertFalse(name == "press_tr.api" or name.startswith("press_tr.api."))
