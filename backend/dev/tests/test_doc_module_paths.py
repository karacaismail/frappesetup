"""Module paths in the backend documents must point to folders that exist.

The platform_core modules got English names (CP2 rename): kimlik -> identity, kabuk -> shell,
yapay_zeka -> ai, model_gecidi -> model_gateway, erisim -> access, mobil -> mobile. Some documents
still pointed at the old folders. A decision text keeps its old wording, with the new name beside
it: an old path may stay when the same line also names the new path. The test checks code paths:

- a file path "platform_core/platform_core/<name>",
- a Python path "platform_core.<name>",
- a short code path in backticks such as `erisim/tests/` or `kimlik.api.x`,
- a contract file name "platform_core-<name>.openapi.yaml".

dev/naming records the rename itself, so it is not checked.
"""

import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "apps" / "platform_core" / "platform_core"
OLD = ("kimlik", "kabuk", "yapay_zeka", "model_gecidi", "erisim", "mobil")
SKIP = ("dev/naming/",)

FILE_PATH = re.compile(r"platform_core/platform_core/([A-Za-z0-9_.-]+)")
PYTHON_PATH = re.compile(r"(?<![\w/.-])platform_core\.([a-z_][a-z0-9_]*)")
SHORT_PATH = re.compile(rf"`(?:\.\./)?({'|'.join(OLD)})[/.](?!localhost)[^`]*`")
CONTRACT = re.compile(r"platform_core-[a-z-]+\.openapi\.yaml")
NEW = dict(zip(OLD, ("identity", "shell", "ai", "model_gateway", "access", "mobile")))


# Folders that hold installed or generated files, not project documents.
IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache"}


def documents():
    names = []
    for path in sorted(BACKEND.rglob("*.md")):
        relative = path.relative_to(BACKEND)
        if IGNORED.isdisjoint(relative.parts) and not relative.as_posix().startswith(SKIP):
            names.append(relative.as_posix())
    return names


def renamed_beside(text, old, line):
    """True when the line also carries the path with the new module name."""
    return text.replace(old, NEW[old], 1) in line


def module_exists(name):
    return (PACKAGE / name).is_dir() or (PACKAGE / f"{name}.py").is_file()


class DocumentModulePaths(unittest.TestCase):
    def test_package_has_the_english_module_folders(self):
        for name in ("identity", "shell", "ai", "model_gateway", "access", "mobile"):
            with self.subTest(module=name):
                self.assertTrue((PACKAGE / name).is_dir())
        for name in OLD:
            with self.subTest(old=name):
                self.assertFalse((PACKAGE / name).exists())

    def test_document_paths_point_to_existing_modules(self):
        problems = []
        for name in documents():
            for number, line in enumerate((BACKEND / name).read_text().splitlines(), 1):
                where = f"{name}:{number}"
                for match in FILE_PATH.finditer(line):
                    segment = match.group(1).rstrip(".")
                    if segment in NEW and renamed_beside(match.group(0), segment, line):
                        continue
                    if "*" not in segment and not (PACKAGE / segment).exists():
                        problems.append(f"{where}: {match.group(0)}")
                for match in PYTHON_PATH.finditer(line):
                    if match.group(1) in NEW and renamed_beside(match.group(0), match.group(1), line):
                        continue
                    if not module_exists(match.group(1)):
                        problems.append(f"{where}: {match.group(0)}")
                for match in CONTRACT.finditer(line):
                    if not (BACKEND / "contracts" / match.group(0)).is_file():
                        problems.append(f"{where}: {match.group(0)}")
                for match in SHORT_PATH.finditer(line):
                    if renamed_beside(match.group(0), match.group(1), line):
                        continue
                    problems.append(f"{where}: {match.group(0)}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
