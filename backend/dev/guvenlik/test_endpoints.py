"""Regression tests for the static Frappe endpoint inventory."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

from endpoints import main


class EndpointInventoryTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.backend = Path(directory.name)
        self.package = self.backend / "apps" / "demo" / "demo"
        self.package.mkdir(parents=True)

    def write(self, relative_path, source):
        path = self.package / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(source), encoding="utf-8")

    def check(self):
        output = io.StringIO()
        errors = io.StringIO()
        with patch("sys.argv", ["endpoints.py", str(self.backend)]):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = main()
        return status, output.getvalue(), errors.getvalue()

    def test_reports_guest_routes_and_methods(self):
        self.write(
            "api/__init__.py",
            """
            from frappe import whitelist as publish
            from frappe.rate_limiter import rate_limit

            @publish(allow_guest=True, methods=["POST"])
            @rate_limit(limit=5, seconds=60)
            def begin():
                return "test"
            """,
        )
        self.write(
            "api/test___init__.py",
            """
            import unittest

            class TestBegin(unittest.TestCase):
                def test_begin_guest_denied(self):
                    self.assertTrue(True)

                def test_begin_foreign_data_denied(self):
                    self.assertTrue(True)
            """,
        )
        status, output, errors = self.check()
        self.assertEqual(status, 0, errors)
        self.assertIn("/api/method/demo.api.begin", output)
        self.assertIn("POST", output)
        self.assertEqual(output.count("/api/method/demo.api.begin"), 2)

    def test_reviewed_logout_still_requires_exact_route_and_line(self):
        self.package = self.backend / "apps" / "press_tr" / "press_tr"
        self.write(
            "api/__init__.py",
            "import frappe\n@frappe.whitelist(allow_guest=True, methods=['POST'])\n"
            "def keycloak_backchannel_logout(): pass\n"
            "@frappe.whitelist(allow_guest=True, methods=['POST'])\ndef other(): pass\n",
        )
        self.write(
            "api/test___init__.py",
            "def test_keycloak_backchannel_logout_guest_denied(): pass\n"
            "def test_keycloak_backchannel_logout_foreign_data_denied(): pass\n"
            "def test_other_guest_denied(): pass\ndef test_other_foreign_data_denied(): pass\n",
        )
        path = "backend/apps/press_tr/press_tr/api/__init__.py"
        rule = "frappe-guest-without-limit"
        with patch("endpoints.approved_keys", return_value={(rule, path, 2), (rule, path, 4)}):
            status, _, errors = self.check()
        self.assertEqual(status, 1)
        self.assertEqual(errors.count("rate_limit"), 1)
        self.assertIn(":5 rate_limit", errors)
        with patch("endpoints.approved_keys", return_value={(rule, path, 4)}):
            _, _, errors = self.check()
        self.assertEqual(errors.count("rate_limit"), 2)

    def test_tests_in_another_module_do_not_count(self):
        for module in ("first", "second"):
            self.write(
                f"{module}.py",
                """
                import frappe as framework

                @framework.whitelist(methods=["GET"])
                async def read():
                    return "test"
                """,
            )
        self.write(
            "test_first.py",
            """
            def test_read_guest_denied():
                assert True

            def test_read_foreign_data_denied():
                assert True
            """,
        )
        status, output, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("/api/method/demo.first.read", output)
        self.assertIn("/api/method/demo.second.read", output)
        self.assertIn("test_second.py", errors)
        self.assertIn("test_read_guest_denied", errors)
        self.assertIn("test_read_foreign_data_denied", errors)
        self.assertNotIn("test_first.py", errors)

    def test_unresolved_guest_mode_fails(self):
        self.write(
            "api.py",
            """
            import frappe

            @frappe.whitelist(allow_guest=GUEST_MODE, methods=["GET"])
            def read():
                return "test"
            """,
        )
        status, _, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("allow_guest", errors)

    def test_document_methods_have_scoped_test_names(self):
        self.write(
            "record.py",
            """
            import frappe

            class Record:
                @frappe.whitelist(methods=["POST"])
                def submit(self):
                    return "test"
            """,
        )
        status, output, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("demo.record.Record.submit", output)
        self.assertNotIn("/api/method/demo.record.Record.submit", output)
        self.assertIn("test_Record_submit_guest_denied", errors)
        self.assertIn("test_Record_submit_foreign_data_denied", errors)

    def test_positional_guest_rejects_limiter_above_whitelist(self):
        self.write(
            "api.py",
            """
            import frappe
            from frappe.rate_limiter import rate_limit

            @rate_limit(limit=5, seconds=60)
            @frappe.whitelist(True, methods=["GET"])
            def read():
                return "test"
            """,
        )
        status, _, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("rate_limit", errors)

    def test_empty_method_list_reports_failure(self):
        self.write(
            "api.py",
            """
            from frappe import whitelist as publish

            @publish(methods=[])
            def read():
                return "test"
            """,
        )
        status, _, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("methods", errors)

    def test_missing_apps_reports_failure(self):
        self.backend = self.backend / "missing"
        status, _, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("apps", errors)

    def test_unparseable_source_reports_failure(self):
        self.write("api.py", "def invalid(\n")
        status, _, errors = self.check()
        self.assertEqual(status, 1)
        self.assertIn("api.py", errors)


if __name__ == "__main__":
    unittest.main()
