"""Check the evidence rules used by the 20-request gateway test."""

import unittest
from decimal import Decimal

from platform_core.model_gateway.tests import concurrency


class ConcurrencyEvidenceTests(unittest.TestCase):
	def test_a_committed_reservation_above_budget_fails(self):
		with self.assertRaisesRegex(AssertionError, "budget"):
			concurrency.check_reservations([Decimal("0.012"), Decimal("0.061")])

	def test_duplicate_provider_dispatch_fails(self):
		with self.assertRaisesRegex(AssertionError, "provider"):
			concurrency.check_dispatches({"Concurrency fixture 1"}, ["Concurrency fixture 1"] * 2)
