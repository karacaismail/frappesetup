import ast
import unittest

from source import sql_calls, walk


class SqlAccessTests(unittest.TestCase):
    def test_raw_cursor_and_connection_references(self):
        for expression in (
            "frappe.db._cursor",
            "frappe.local.db._conn",
            "getattr(frappe.db, '_cursor')",
            "database._conn",
            "frappe.db.get_connection().cursor()",
        ):
            with self.subTest(expression=expression):
                tree = ast.parse(f"database = frappe.db\nconnection = {expression}\n")
                self.assertEqual(list(sql_calls(walk(tree), {})), [2])

    def test_unrelated_cursor_and_connection_references(self):
        tree = ast.parse("cursor = other_db._cursor\nconnection = other_db._conn\n")
        self.assertEqual(list(sql_calls(walk(tree), {})), [])
