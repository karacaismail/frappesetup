"""Check O-35 before the benchmark creates or deletes data."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from . import performance_data as data


class PerformanceSafetyTest(unittest.TestCase):
    def test_wrong_site_or_missing_opt_in_stops_before_connecting(self):
        for site, enabled in (
            ("test-mobile.localhost", 1),
            ("perf-mobile.example.test", 1),
            ("perf-mobile.localhost", 0),
        ):
            with self.subTest(site=site, enabled=enabled):
                frappe = Mock()
                frappe.get_file_json.return_value = {"allow_performance_fixture": enabled}
                with patch.object(data, "frappe", frappe), self.assertRaises(SystemExit):
                    with data.test_database(site):
                        self.fail("The site was accepted")
                frappe.connect.assert_not_called()

    def test_nonempty_queue_stops_before_any_seed_writes(self):
        frappe = Mock()
        frappe.get_file_json.return_value = {"allow_performance_fixture": 1}
        for ready, deferred in ((1, 0), (0, 1)):
            connection = Mock()
            connection.zcard.side_effect = {"started": 0, "deferred": deferred, "scheduled": 0}.__getitem__
            queue = SimpleNamespace(
                count=ready,
                connection=connection,
                started_job_registry=SimpleNamespace(key="started"),
                deferred_job_registry=SimpleNamespace(key="deferred"),
                scheduled_job_registry=SimpleNamespace(key="scheduled"),
            )
            with (
                self.subTest(ready=ready, deferred=deferred),
                patch.object(data, "frappe", frappe),
                patch.object(data, "get_queues", return_value=[queue]),
                self.assertRaisesRegex(SystemExit, "queue"),
            ):
                data.seed_site("perf-mobile.localhost", 1, [])
        self.assertEqual(frappe.db.mock_calls, [])

    def test_seed_tracks_only_a_counter_it_creates(self):
        for already_exists in (False, True):
            frappe = Mock()
            frappe.get_file_json.return_value = {"allow_performance_fixture": 1}
            frappe.get_installed_apps.return_value = ["erpnext", "hrms", "platform_core", "mobile_test_app"]
            frappe.db.count.return_value = 0
            frappe.db.exists.return_value = already_exists
            created = []
            with (
                self.subTest(already_exists=already_exists),
                patch.object(data, "frappe", frappe),
                patch.object(data, "get_queues", return_value=[]),
                patch.object(data, "EMPLOYEES", 0),
                patch.object(data, "now_datetime", return_value="fixture-time"),

                patch.object(data, "seed_sequence") as seed,
                patch.object(data, "MobileStore"),
            ):
                data.seed_site("perf-mobile.localhost", 0, created)
            self.assertEqual(seed.call_count, int(not already_exists))
            self.assertEqual(("Mobile Sequence", "site") in created, not already_exists)

    def test_cleanup_selects_the_doctype_and_name_together(self):
        frappe = Mock()
        with patch.object(data, "frappe", frappe):
            data.delete_records([("Company", "same-name")])
        self.assertEqual(frappe.db.delete.call_args_list, [call("Company", {"name": ["in", ["same-name"]]})])
