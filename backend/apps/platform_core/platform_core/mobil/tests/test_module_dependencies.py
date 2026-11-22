"""Keep mobile metadata helpers independent from the services using them."""

import ast
import unittest
from pathlib import Path


class MobileModuleDependenciesTest(unittest.TestCase):
	def test_store_and_sessions_do_not_import_each_other(self):
		root = Path(__file__).resolve().parents[1]

		def imports(module, dependency):
			tree = ast.parse((root / f"{module}.py").read_text())
			return any(
				node.level == 1 and node.module == dependency
				for node in ast.walk(tree)
				if isinstance(node, ast.ImportFrom)
			)

		self.assertFalse(imports("store", "sessions") and imports("sessions", "store"))
