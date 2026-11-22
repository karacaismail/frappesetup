"""Check the O-31 sampling and budget without starting Frappe."""

import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from platform_core.shell import measure_performance as benchmark
from platform_core.shell.measure_performance import LIMIT_MS, SAMPLES, summarize


class TestPerformanceBudget(TestCase):
	def test_budget_uses_nearest_rank_and_includes_the_boundary(self):
		p95, passed = summarize([10.0] * 47 + [LIMIT_MS, 900.0, 950.0])
		self.assertEqual(p95, 500.0)
		self.assertTrue(passed)

	def test_budget_rejects_a_p95_above_the_limit(self):
		p95, passed = summarize([10.0] * 47 + [500.01, 900.0, 950.0])
		self.assertEqual(p95, 500.01)
		self.assertFalse(passed)

	def test_budget_rejects_fewer_than_fifty_samples(self):
		with self.assertRaises(ValueError):
			summarize([10.0] * (SAMPLES - 1))

	def test_warm_bootstrap_budget_rejects_above_two_hundred(self):
		self.assertEqual(summarize([200.01] * SAMPLES, limit_ms=200), (200.01, False))

	def test_report_translates_labels_without_changing_the_budget(self):
		catalog = Path(benchmark.__file__).parents[1] / "translations" / "tr.csv"
		with catalog.open(encoding="utf-8", newline="") as translation_file:
			translations = {
				source: translated
				for source, translated, context in csv.reader(translation_file)
				if context == "shell.performance"
			}

		def translate(source, *, context):
			self.assertEqual(context, "shell.performance")
			return translations[source]

		framework = SimpleNamespace(__version__="16.56.0", _=translate)
		app = SimpleNamespace(__version__="16.55.0")
		rows = [(benchmark.BOOTSTRAP_LABEL, benchmark.WARM_MODE, [201.0] * SAMPLES)]
		with patch.dict(sys.modules, {"frappe": framework, "erpnext": app, "hrms": app}):
			report, passed = benchmark.report(rows)

		self.assertFalse(passed)
		self.assertIn("### O-31 kabuk ölçümü", report)
		self.assertIn(
			"| Aç\u0131l\u0131ş verisi | Önbellekli | 50 | 201.000 | 201.000 | 200 | fail |", report
		)


class TestPerformanceFixture(TestCase):
	def test_rejects_invalid_site_before_initializing_frappe(self):
		frappe = Mock()
		with (
			patch.dict(sys.modules, {"frappe": frappe}),
			self.assertRaisesRegex(RuntimeError, "perf-"),
			benchmark.test_database("production.localhost"),
		):
			self.fail("The fixture database was opened.")
		frappe.init.assert_not_called()

	def test_requires_explicit_site_opt_in(self):
		frappe = Mock()
		frappe.conf.get.return_value = 1
		with (
			patch.dict(sys.modules, {"frappe": frappe}),
			patch.object(benchmark.Path, "read_text", return_value="{}"),
			self.assertRaisesRegex(RuntimeError, "allow_performance_fixture"),
		):
			with benchmark.test_database("perf-kabuk.localhost"):
				self.fail("The fixture database was opened.")
		frappe.connect.assert_not_called()

	def test_nonempty_queue_stops_before_any_fixture_operation(self):
		frappe = Mock()
		with (
			patch.object(benchmark, "test_database", return_value=MagicMock()) as database,
			patch.dict(
				sys.modules, {"frappe.utils.background_jobs": Mock(get_queues=lambda: [Mock(count=1)])}
			),
			patch.dict(sys.modules, {"frappe.utils": Mock(), "frappe.utils.password": Mock()}),
			self.assertRaisesRegex(RuntimeError, "queue"),
		):
			database.return_value.__enter__.return_value = frappe
			benchmark.seed_site("perf-kabuk.localhost", [])
		self.assertEqual(frappe.mock_calls, [])

	def test_cleanup_preserves_same_name_in_another_doctype(self):
		frappe = Mock()
		rows = {("Company", "shared"), ("Leave Type", "shared")}
		frappe.db.delete.side_effect = lambda doctype, filters: rows.remove((doctype, filters["name"]))
		with patch.object(benchmark, "test_database", return_value=MagicMock()) as database:
			database.return_value.__enter__.return_value = frappe
			benchmark.cleanup_fixture("perf-kabuk.localhost", [("Company", "shared")])
		self.assertEqual(rows, {("Leave Type", "shared")})
		frappe.db.commit.assert_called_once()
