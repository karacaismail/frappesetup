"""Check O-31 measurement arithmetic and fail-closed sample requirements."""

import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from platform_core.model_gecidi.tests import performance


class GatewayPerformanceTests(unittest.TestCase):
	def test_p95_uses_unrounded_server_time_without_provider_wait(self):
		samples = [(0.820, 0.320)] * 48 + [(0.900, 0.100), (1.000, 0.001)]
		report = performance.summarize(samples, limit_ms=500)
		self.assertEqual(report["samples"], 50)
		self.assertEqual(report["gateway_p95_ms"], 500.0)
		self.assertEqual(report["provider_p95_ms"], 320.0)
		self.assertTrue(report["pass"])

	def test_samples_below_minimum_are_rejected(self):
		with self.assertRaises(ValueError):
			performance.summarize([(0.003, 0.0)] * 49, limit_ms=500)

	def test_wrong_site_or_missing_opt_in_stops_before_writes(self):
		for site, opt_in in (
			("test-platform-core.localhost", 1),
			("perf-gateway.example.com", 1),
			("perf-gateway.localhost", 0),
			("perf-gateway.localhost", "true"),
			("perf-gateway.localhost", "1.0"),
			("perf-gateway.localhost", "null"),
		):
			with (
				self.subTest(site=site, opt_in=opt_in),
				patch.object(performance, "frappe") as framework,
				patch.object(performance, "_prepare_load") as prepare,
				patch("frappe.utils.background_jobs.get_queues") as queues,
			):
				framework.local.site = site
				framework.local.site_path = "sites/fixture"
				self.enterContext(
					patch.object(
						performance.Path,
						"read_text",
						return_value=f'{{"allow_performance_fixture": {opt_in}}}',
					)
				)
				framework.conf = {"allow_tests": 1, "allow_performance_fixture": 1}
				with self.assertRaisesRegex(RuntimeError, "perf-"):
					performance.run()
				prepare.assert_not_called()
				queues.assert_not_called()

	def test_nonempty_queue_stops_without_creating_data_or_running_jobs(self):
		queue = Mock(count=1)
		with (
			patch.object(performance, "frappe") as framework,
			patch("frappe.utils.background_jobs.get_queues", return_value=[queue]) as queues,
			patch.object(performance, "_prepare_load") as prepare,
		):
			framework.local.site = "perf-gateway.localhost"
			framework.local.site_path = "sites/fixture"
			self.enterContext(
				patch.object(performance.Path, "read_text", return_value='{"allow_performance_fixture": 1}')
			)
			framework.conf = {"allow_performance_fixture": 1}
			with self.assertRaisesRegex(RuntimeError, "queue"):
				performance.run()
			queues.assert_called_once_with()
			prepare.assert_not_called()
			self.assertEqual(queue.mock_calls, [])

	def test_cleanup_deletes_only_fixture_doctype_and_name_pairs(self):
		records = {}
		with (
			patch.object(performance, "frappe") as framework,
			patch("frappe.utils.background_jobs.get_queues", return_value=[]),
			patch.object(performance, "_gateway_fixture", return_value=nullcontext({})),
			patch.object(performance, "_collect", return_value={}),
			patch.object(performance, "uuid4", return_value=SimpleNamespace(hex="12345678abcd")),
			patch("builtins.print"),
		):
			framework.local.site = "perf-gateway.localhost"
			framework.local.site_path = "sites/fixture"
			self.enterContext(
				patch.object(performance.Path, "read_text", return_value='{"allow_performance_fixture": 1}')
			)
			framework.conf = {
				"allow_performance_fixture": 1,
				"model_gateway_user_requests_per_minute": 200,
			}
			framework.db.count.return_value = 0

			def insert(doctype, _fields, rows):
				records.update({(doctype, row[0]): row[1] for row in rows})
				if doctype == "Leave Application":
					leave, employee = rows[0][:2]
					records[("ToDo", leave)] = None
					records[("Leave Application", "Unrelated leave")] = employee

			def delete(doctype, filters):
				self.assertEqual(set(filters), {"name"})
				for name in filters["name"][1]:
					records.pop((doctype, name))

			framework.db.bulk_insert.side_effect = insert
			framework.db.delete.side_effect = delete
			performance.run()

		self.assertEqual(
			records,
			{
				("ToDo", "Gateway Bench 12345678-0000-00"): None,
				("Leave Application", "Unrelated leave"): "Gateway Bench 12345678-0000",
			},
		)
