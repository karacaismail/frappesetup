"""Exercise the interface inventory through its public command."""

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

GATE = Path(__file__).with_name("gate.py").resolve()
SCRATCH = GATE.parents[3] / ".pane" / "scratch"
APP = "apps/sample_app/sample_app"


class InterfaceInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.write(
            "AGENTS.md",
            """
            ## Klasörler ve sahipleri

            | Klasör | İçerik | Sahip iş |
            | --- | --- | --- |
            | `apps/sample_app/` iskeleti | `hooks.py` | shared-owner |
            | `apps/sample_app/sample_app/cards/`, `api/cards.py` | Cards | cards-owner |
            | `apps/sample_app/sample_app/requests/` | Requests | requests-owner |
            """,
        )
        self.write(
            "dev/module-boundaries.json",
            json.dumps(
                {
                    "modules": {"sample_app.cards": [], "sample_app.requests": ["sample_app.cards"]},
                    "path_owners": {"sample_app.api.cards": "sample_app.cards"},
                    "public_paths": {"sample_app.cards": ["sample_app.cards.api", "sample_app.api.cards"]},
                }
            ),
        )

    def write(self, path, body):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")

    def inventory(self):
        result = subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, "--list-interfaces"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def test_lists_methods_hooks_events_and_owners(self):
        self.write(f"{APP}/api/cards.py", "import frappe\n@frappe.whitelist()\ndef read(): pass")
        self.write(f"{APP}/cards/events.py", "def update(): pass\ndef clear(): pass")
        self.write(
            f"{APP}/hooks.py",
            """
            clear_cache = ["sample_app.cards.events.clear"]
            doc_events = {"Contact": {"on_update": "sample_app.cards.events.update"}}
            fixtures = [{"dt": "Role", "filters": [["name", "=", "AI Manager"]]}]
            """,
        )
        first = self.inventory()
        self.assertEqual(first, self.inventory())
        self.assertIn("## `sample_app.cards`", first)
        for name in (
            "sample_app.api.cards.read",
            "sample_app.cards.events.clear",
            "sample_app.cards.events.update",
        ):
            self.assertTrue(any(name in row and "cards-owner" in row for row in first.splitlines()), first)
        self.assertIn("clear_cache", first)
        self.assertIn("Contact", first)
        self.assertIn("on_update", first)
        self.assertIn('fixtures[filters] = ["name", "=", "AI Manager"]', first)
        self.assertTrue(any("fixtures" in row and "shared-owner" in row for row in first.splitlines()))

    def test_internal_cross_module_imports_warn_without_failing(self):
        self.write(f"{APP}/cards/api.py", "def read(): pass\ndef _private(): pass")
        self.write(f"{APP}/cards/internal.py", "def cleanup(): pass")
        self.write(f"{APP}/cards/nearby.py", "from .api import _private")
        self.write(
            f"{APP}/requests/service.py",
            """
            from ..cards.api import read as load, _private
            from ..cards import internal as ops

            def refresh():
                return ops.cleanup()
            """,
        )
        report, warnings = self.inventory().split("## İç işlev içe aktarma uyarıları")
        self.assertIn("sample_app.cards.api.read", report)
        self.assertIn("requests/service.py:1", report)
        self.assertNotIn("sample_app.cards.api.read", warnings)
        self.assertIn("sample_app.cards.api._private", warnings)
        self.assertIn("sample_app.cards.internal.cleanup", warnings)
        self.assertIn("requests/service.py:1", warnings)
        self.assertIn("requests/service.py:2", warnings)
        self.assertNotIn("cards/nearby.py", warnings)

    def test_public_reexport_includes_imported_function_without_warning(self):
        self.write(f"{APP}/cards/internal.py", "def read(): pass")
        self.write(f"{APP}/cards/api.py", "from .internal import read as read_card")
        self.write(f"{APP}/requests/service.py", "from ..cards.api import read_card")
        report, warnings = self.inventory().split("## İç işlev içe aktarma uyarıları")
        self.assertIn("sample_app.cards.api.read_card", report)
        self.assertIn("requests/service.py:1", report)
        self.assertNotIn("sample_app.cards.api.read_card", warnings)
