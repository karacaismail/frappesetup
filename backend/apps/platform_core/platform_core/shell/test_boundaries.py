import ast
import unittest
from pathlib import Path


class TestShellBoundary(unittest.TestCase):
	def test_shell_code_only_imports_its_own_platform_module(self):
		shell = Path(__file__).parent
		root = shell.parent
		sources = [
			root / "api" / "meta.py",
			root / "api" / "shell.py",
			root / "www" / "panel.py",
			*(path for path in shell.glob("*.py") if not path.stem.startswith("test_")),
		]
		for source in sources:
			tree = ast.parse(source.read_text(encoding="utf-8"))
			for node in ast.walk(tree):
				if isinstance(node, ast.Import):
					modules = [alias.name for alias in node.names]
				elif isinstance(node, ast.ImportFrom):
					modules = [node.module or ""]
					if node.module == "platform_core":
						modules = [f"platform_core.{alias.name}" for alias in node.names]
				else:
					continue
				for module in modules:
					if module.startswith("platform_core."):
						with self.subTest(file=source.name, module=module):
							self.assertEqual(module.split(".")[1], "shell")
