"""Check O-31 measurement arithmetic and fail-closed sample requirements."""

import unittest

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
