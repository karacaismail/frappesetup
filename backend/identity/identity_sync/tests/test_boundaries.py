"""Modül sınırının otomatik denetimi (B-10).

Servis yalnız Python'un kendi kitaplığını ve ortak `oidc_verify` kitaplığını kullanır.
Servis site kodunu ve model sağlayıcısı kitaplığını içe aktarmaz.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import unittest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "identity_sync"
ALLOWED_EXTERNAL = {"oidc_verify"}
SCHEDULER_MODULES = {"sched", "crontab", "schedule", "apscheduler"}


def imported_modules(path: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


class BoundaryTest(unittest.TestCase):
    def test_package_has_sources(self) -> None:
        self.assertGreater(len(list(PACKAGE.glob("*.py"))), 5)

    def test_only_standard_library_and_approved_imports(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"identity_sync"} | ALLOWED_EXTERNAL
        for path in sorted(PACKAGE.glob("**/*.py")):
            with self.subTest(file=path.name):
                self.assertEqual(imported_modules(path) - allowed, set())

    def test_oidc_verify_is_imported_only_by_server_auth(self) -> None:
        users = [p.name for p in sorted(PACKAGE.glob("**/*.py")) if "oidc_verify" in imported_modules(p)]
        self.assertEqual(users, ["auth.py"])

    def test_no_scheduler_module(self) -> None:
        # Zamanlanmış iş yasaktır (Proje kaydı D-6).
        for path in sorted(PACKAGE.glob("**/*.py")):
            with self.subTest(file=path.name):
                self.assertEqual(imported_modules(path) & SCHEDULER_MODULES, set())

    def test_pure_modules_do_not_touch_network_or_disk(self) -> None:
        impure = {"urllib", "http", "socket", "sqlite3", "os", "subprocess", "time"}
        for name in ("mapping.py", "events.py", "reconcile.py"):
            with self.subTest(file=name):
                self.assertEqual(imported_modules(PACKAGE / name) & impure, set())


if __name__ == "__main__":
    unittest.main()
