"""Check performance reporting and safeguards without connecting to a site or a queue."""

import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import call, patch

import measure


class PerformanceReportTest(unittest.TestCase):
    def test_report_renders_p95_budget_results_as_markdown(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = measure.report(
                "abcdef0",
                {
                    ("GET", "/read", 500): [20.0] * 18 + [500.0, 520.0],
                    ("POST", "/write", 1000): [900.0, 1010.0],
                },
            )

        self.assertEqual(exit_code, 1)
        lines = output.getvalue().splitlines()
        self.assertIn("## HRMS TR O-31 performance report", lines)
        self.assertIn("Git revision `abcdef0`.", lines)
        self.assertIn("| Method and route | Calls | p95 (ms) | Budget (ms) | Result |", lines)
        self.assertIn("| `GET /read` | 20 | 500.00 | 500 | pass |", lines)
        self.assertIn("| `POST /write` | 2 | 1010.00 | 1000 | fail |", lines)


class PerformanceSafetyTest(unittest.TestCase):
    def test_wrong_site_is_rejected_before_initializing_frappe(self):
        with patch.object(measure, "frappe") as framework:
            with self.assertRaisesRegex(SystemExit, "perf-"):
                measure.make_workload("test-hrms.localhost", "synthetic")
            framework.init.assert_not_called()

    def test_missing_site_opt_in_blocks_data_creation(self):
        with patch.object(measure, "frappe") as framework:
            framework.conf = SimpleNamespace(allow_performance_fixture=1)
            framework.get_file_json.return_value = {}
            with self.assertRaisesRegex(SystemExit, "allow_performance_fixture"):
                measure.make_workload("perf-hrms.localhost", "synthetic")
            framework.connect.assert_not_called()
            framework.get_doc.assert_not_called()

    def test_nonempty_queue_blocks_data_creation(self):
        with (
            patch.object(measure, "frappe") as framework,
            patch.object(measure, "get_queues", create=True, return_value=[SimpleNamespace(count=1)]),
        ):
            framework.get_file_json.return_value = {"allow_performance_fixture": 1}
            with self.assertRaisesRegex(SystemExit, "queue"):
                measure.make_workload("perf-hrms.localhost", "synthetic")
            framework.get_doc.assert_not_called()
            framework.set_user.assert_not_called()

    def test_cleanup_does_not_delete_same_name_in_another_doctype(self):
        owned = ("Leave Application", "shared-name")
        unrelated = ("Attendance Request", "shared-name")
        rows = {owned, unrelated}
        with patch.object(measure, "frappe") as framework:
            framework.get_doc.return_value.docstatus = 0
            framework.db.exists.side_effect = lambda doctype, name: (doctype, name) in rows
            framework.delete_doc.side_effect = lambda doctype, name, **kwargs: rows.remove((doctype, name))
            measure.cleanup_records([owned])
            self.assertEqual(framework.delete_doc.call_args_list, [call(*owned, delete_permanently=True)])
            self.assertEqual(rows, {unrelated})


if __name__ == "__main__":
    unittest.main()
