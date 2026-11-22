"""Regression tests for dispatch and quota settlement."""

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from platform_core.model_gecidi import adapters, gateway, ledger, routing


class DispatchTests(unittest.TestCase):
	def test_long_completion_has_more_read_time_than_short_completion(self):
		self.assertGreater(gateway.read_timeout(4096), gateway.read_timeout(128))
		self.assertGreater(gateway.read_timeout(16384), 10)
		self.assertLess(gateway.read_timeout(16384), gateway.MAX_ROUTE_SECONDS)

	def test_pending_and_unknown_attempts_reserve_only_estimated_cost(self):
		account = SimpleNamespace(name="fixture", has_monthly_budget=True, currency="USD", monthly_budget=10)
		pending = SimpleNamespace(result="pending", reservation_known=1, reserved_cost="2", currency="USD")
		unknown = SimpleNamespace(result="unknown", reservation_known=1, reserved_cost="3", currency="USD")
		with patch.object(ledger, "_usage", return_value=[pending, unknown]):
			with patch.object(ledger, "now_datetime", return_value=datetime(2026, 1, 1)):
				self.assertEqual(ledger.remaining(account), Decimal(5))

	def test_lost_reservation_is_settled_without_calling_the_provider(self):
		target = Mock()
		target.account.has_monthly_budget = True
		entry = routing.Candidate("fixture", "fixture-model")
		lock = Mock()
		lock.owned.return_value = False
		with (
			patch.object(ledger, "finish") as settle,
			patch.object(adapters, "complete") as send,
			self.assertRaises(gateway.Denied),
		):
			gateway._attempt(entry, target, Mock(), 30, float("inf"), lock, "fixture-log")
		send.assert_not_called()
		self.assertEqual(settle.call_args.args[2], "not_sent")

	def test_ambiguous_timeout_cannot_fall_back_for_a_capped_account(self):
		self.assertFalse(gateway.retry_allowed("timeout", potentially_billed=True, capped=True))
		self.assertTrue(gateway.retry_allowed("timeout", potentially_billed=False, capped=True))
		self.assertTrue(gateway.retry_allowed("timeout", potentially_billed=True, capped=False))

	def test_unbilled_provider_rejection_releases_estimate(self):
		target = Mock()
		entry = routing.Candidate("fixture", "fixture-model")
		lock = Mock()
		lock.owned.return_value = True
		with (
			patch.object(ledger, "finish") as settle,
			patch.object(adapters, "complete", side_effect=adapters.GatewayError("rejected")),
		):
			gateway._attempt(entry, target, Mock(), 30, float("inf"), lock, "fixture-log")
		self.assertEqual(settle.call_args.args[2], "not_billed")
		self.assertEqual(settle.call_args.kwargs["failure_code"], "rejected")
