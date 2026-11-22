"""HRMS TR depends on public Frappe APIs and provider contracts."""

import ast
import unittest
from graphlib import TopologicalSorter
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

	def test_local_modules_and_framework_document_writes(self):
		root = Path(__file__).resolve().parents[1]
		modules = {path.stem: path for path in root.glob("*.py") if not path.stem.startswith(("test_", "__"))}
		graph = {name: set() for name in modules}
		for name, path in modules.items():
			tree = ast.parse(path.read_text(encoding="utf-8"))
			for node in ast.walk(tree):
				if isinstance(node, ast.Import):
					for item in node.names:
						parts = item.name.split(".")
						if len(parts) > 1 and parts[0] == "hrms_tr" and parts[1] in modules:
							graph[name].add(parts[1])
				elif isinstance(node, ast.ImportFrom) and node.module:
					if node.module == "hrms_tr":
						graph[name].update(item.name for item in node.names if item.name in modules)
					elif node.module.startswith("hrms_tr."):
						target = node.module.split(".")[1]
						if target in modules:
							graph[name].add(target)
				elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
					self.assertNotIn(
						node.func.attr,
						{"db_set", "db_insert", "db_update", "db_delete"},
						f"{path.name}:{node.lineno}",
					)
					if ast.unparse(node.func).startswith("frappe.db."):
						self.assertNotIn(
							node.func.attr,
							{"set_value", "delete", "insert", "sql", "truncate"},
							f"{path.name}:{node.lineno}",
						)
		TopologicalSorter(graph).prepare()
