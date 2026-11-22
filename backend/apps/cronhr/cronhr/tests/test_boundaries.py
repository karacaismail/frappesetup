"""CronHR depends on public Frappe APIs and provider contracts."""

import ast
import unittest
from pathlib import Path


class ModuleBoundaryTest(unittest.TestCase):
	def test_no_direct_imports_of_provider_internals(self):
		root = Path(__file__).resolve().parents[1]
		for path in root.glob("*.py"):
			with self.subTest(path=path.name):
				imports = ast.walk(ast.parse(path.read_text(encoding="utf-8")))
				for node in imports:
					if isinstance(node, ast.Import):
						for alias in node.names:
							self.assertNotIn(alias.name.split(".")[0], {"platform_core", "hrms"})
					elif isinstance(node, ast.ImportFrom) and node.module:
						self.assertNotIn(node.module.split(".")[0], {"platform_core", "hrms"})
