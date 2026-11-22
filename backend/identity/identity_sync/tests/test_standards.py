"""Checks from docs/standartlar/frappe-python-disi-standartlari.md that a machine can hold.

Rule ids are in the test names' comments. The expected values come from the standard, not from the code.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from .test_contract import CONTRACT

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
HTTP_METHODS = ("get", "post", "put", "patch", "delete")
# Names that existed before the "new names are English" decision (D-12). They are not renamed by hand.
LEGACY_EXECUTION_VALUES = {"yalniz-okur", "otomatik", "yalniz-onay-katmani"}


class NamingTest(unittest.TestCase):
    def test_new_execution_markers_are_english(self) -> None:
        # H-10: code names are English ASCII. Only the three legacy values keep their old names.
        values = {
            operation["x-yurutme"]
            for item in CONTRACT["paths"].values()
            for method, operation in item.items()
            if method in HTTP_METHODS
        }
        new = values - LEGACY_EXECUTION_VALUES
        self.assertEqual(new, {"press-only"})
        for value in new:
            self.assertRegex(value, r"^[a-z]+(-[a-z]+)*$")


class TimeFieldTest(unittest.TestCase):
    def time_fields(self) -> dict[str, dict]:
        found: dict[str, dict] = {}

        def walk(node: object, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    here = f"{path}.{key}"
                    if key.endswith("_at") and isinstance(value, dict):
                        found[here] = value
                    walk(value, here)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(CONTRACT["components"]["schemas"], "schemas")
        return found

    def test_every_time_field_names_its_time_zone(self) -> None:
        # F-6: a field that carries a time of day states the time zone in the contract.
        fields = self.time_fields()
        self.assertGreaterEqual(len(fields), 3)
        for path, schema in fields.items():
            with self.subTest(path=path):
                self.assertIn("UTC", schema.get("description", ""))


class DebtTest(unittest.TestCase):
    def test_every_known_gap_is_recorded_as_debt(self) -> None:
        # L-2: a gap left on purpose is marked as debt with its effect, owner and closing condition.
        text = (PACKAGE / "README.md").read_text(encoding="utf-8")
        section = text.split("## Bilinen eksikler", 1)[1].split("\n## ", 1)[0]
        bullets = [line for line in section.splitlines() if line.startswith("- ")]
        self.assertGreaterEqual(len(bullets), 3)
        for bullet in bullets:
            with self.subTest(bullet=bullet[:50]):
                self.assertTrue(bullet.startswith("- `BORC(mvp)`:"))
                for part in ("Etki:", "Sorumlu:", "Kapanma koşulu:"):
                    self.assertIn(part, bullet)


class SettingsFileTest(unittest.TestCase):
    def test_example_file_carries_exactly_the_settings_the_service_reads(self) -> None:
        # K-8, H-7: the example file has the same keys as the code, each once.
        source = (PACKAGE / "identity_sync" / "config.py").read_text(encoding="utf-8")
        read = {"IDENTITY_SYNC_" + name for name in re.findall(r'\bget\("([A-Z_]+)"', source)}
        lines = (PACKAGE / ".env.example").read_text(encoding="utf-8").splitlines()
        keys = [line.split("=", 1)[0] for line in lines if line and not line.startswith("#")]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), read)

    def test_default_port_matches_the_example_and_the_contract(self) -> None:
        # X-1: one value, written the same way everywhere. The port is PANE_PORT + 5 in development.
        from identity_sync.config import load_settings

        from .test_config_cli import ConfigTest

        env = {key: value for key, value in ConfigTest.ENV.items() if key != "IDENTITY_SYNC_PORT"}
        example = (PACKAGE / ".env.example").read_text(encoding="utf-8")
        self.assertIn(f"IDENTITY_SYNC_PORT={load_settings(env).port}\n", example)


SOURCES = sorted((PACKAGE / "identity_sync").glob("*.py")) + sorted((PACKAGE / "tests").glob("*.py"))


class SuppressionTest(unittest.TestCase):
    def test_every_suppression_names_its_rule_and_has_a_reason_above(self) -> None:
        # frappe-python-standartlari.md, R-2: the tool's rule code, and the reason in a comment of its own.
        marker = re.compile(r"#\s*(type:\s*ignore|noqa|pragma)\b")
        found = 0
        for path in SOURCES:
            if path.name == "test_standards.py":
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines):
                if not marker.search(line):
                    continue
                found += 1
                with self.subTest(place=f"{path.name}:{number + 1}"):
                    self.assertRegex(line, r"type:\s*ignore\[[a-z-]+\]|noqa:\s*[A-Z]+[0-9]+|pragma:\s*no cover")
                    above = number - 1
                    while marker.search(lines[above]):  # several suppressed lines may share one reason
                        above -= 1
                    self.assertTrue(lines[above].lstrip().startswith("#"), "no reason comment above")
        self.assertGreater(found, 0)


class DependencyTest(unittest.TestCase):
    def test_every_third_party_import_is_declared(self) -> None:
        # frappe-python-standartlari.md, T-3: packages the code imports are declared in the project file.
        import ast
        import sys
        import tomllib

        used: set[str] = set()
        for path in sorted((PACKAGE / "identity_sync").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                used |= {name.split(".")[0] for name in names}
        third_party = {name for name in used if name not in sys.stdlib_module_names and name != "identity_sync"}
        project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        declared = list(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            declared += group
        declared_names = {re.split(r"[<>=!~ \[@;]", item, maxsplit=1)[0].replace("-", "_") for item in declared}
        self.assertEqual(third_party, {"oidc_verify"})
        self.assertLessEqual(third_party, declared_names)
