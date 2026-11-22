"""Check the O-31 sampling and budget without starting Frappe."""

from unittest import TestCase

from platform_core.kabuk.measure_performance import LIMIT_MS, SAMPLES, summarize


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
