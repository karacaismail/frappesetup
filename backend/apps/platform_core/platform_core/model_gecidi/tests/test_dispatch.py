"""Regression tests for dispatch and quota settlement."""

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from platform_core.model_gecidi import adapters, gateway, ledger, routing


class DispatchTests(unittest.TestCase):
	def test_output_speed_controls_provider_read_time(self):
		self.assertEqual(gateway.read_timeout(4096, 50), 90)
		self.assertEqual(gateway.read_timeout(16384, 200), 90)

	def test_output_that_cannot_fit_in_route_is_rejected(self):
		with self.assertRaises(gateway.Denied) as failure:
			gateway.read_timeout(4096, 30)
		self.assertEqual(
			(failure.exception.status, failure.exception.code), (400, "output_limit_exceeds_deadline")
		)

	def test_input_reservation_uses_larger_estimate(self):
		request = gateway.policy.Request([{"role": "user", "content": "é" * 1024}], [], None, 10)
		self.assertGreater(gateway.input_token_bound(SimpleNamespace(context_size=128), request), 2048)
		self.assertEqual(gateway.input_token_bound(SimpleNamespace(context_size=4096), request), 4096)

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
		with (
			patch.object(ledger, "is_pending", return_value=False),
			patch.object(ledger, "finish") as settle,
			patch.object(adapters, "complete") as send,
			self.assertRaises(gateway.Denied),
		):
			gateway._attempt(entry, target, Mock(), 30, float("inf"), "fixture-log")
		send.assert_not_called()
		self.assertEqual(settle.call_args.args[2], "not_sent")

	def test_ambiguous_timeout_cannot_fall_back_for_a_capped_account(self):
		self.assertFalse(gateway.retry_allowed("timeout", capped=True))
		self.assertTrue(gateway.retry_allowed("timeout", capped=False))

	def test_unbilled_provider_rejection_releases_estimate(self):
		target = Mock()
		entry = routing.Candidate("fixture", "fixture-model")
		with (
			patch.object(ledger, "is_pending", return_value=True),
			patch.object(ledger, "finish") as settle,
			patch.object(adapters, "complete", side_effect=adapters.GatewayError("rejected")),
		):
			gateway._attempt(entry, target, Mock(), 30, float("inf"), "fixture-log")
		self.assertEqual(settle.call_args.args[2], "not_billed")
		self.assertEqual(settle.call_args.kwargs["failure_code"], "rejected")

	def test_api_moved_to_another_account_cannot_use_old_account_quota(self):
		account = SimpleNamespace(name="original", enabled=1)
		api = SimpleNamespace(name="fixture", account="original", modified="initial")
		model = SimpleNamespace(context_size=128, prices_known=0)
		target = SimpleNamespace(account=account, api=api, model=model, provider=Mock())
		request = gateway.policy.Request([{"role": "user", "content": "test"}], [], None, 12)
		moved_api = SimpleNamespace(account="other", enabled=1, modified="moved")
		with (
			patch.object(gateway.frappe, "db", Mock()),
			patch.object(gateway.frappe, "session", SimpleNamespace(user="fixture")),
			patch.object(gateway, "scoped_lock"),
			patch.object(gateway, "lock_row", side_effect=[account, moved_api]),
			patch.object(ledger, "remaining", return_value=None),
			patch.object(ledger, "api_quota", return_value=True),
			patch.object(ledger, "site_quota", return_value=True),
			patch.object(ledger, "begin") as begin,
			self.assertRaises(gateway.Denied),
		):
			gateway._reserve(None, target, request)
		begin.assert_not_called()

	def test_denied_destination_is_a_no_send_attempt(self):
		target = Mock()
		entry = routing.Candidate("fixture", "fixture-model")
		with (
			patch.object(ledger, "is_pending", return_value=True),
			patch.object(ledger, "finish") as settle,
			patch.object(
				adapters,
				"complete",
				side_effect=adapters.GatewayError("endpoint_unavailable", may_be_billed=False),
			),
			self.assertRaises(gateway.Denied) as failure,
		):
			gateway._attempt(entry, target, Mock(), 30, float("inf"), "fixture-log")
		self.assertEqual((failure.exception.status, failure.exception.code), (503, "endpoint_unavailable"))
		self.assertEqual(settle.call_args.args[2], "not_sent")
