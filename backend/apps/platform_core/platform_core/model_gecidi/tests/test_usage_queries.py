"""Tests for bounded and stable usage-log reads."""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from platform_core.model_gecidi import ledger, maintenance


class UsageQueryTests(unittest.TestCase):
	def test_all_usage_is_read_in_bounded_name_order(self):
		filters = {"account": "account"}
		pages = [[SimpleNamespace(name="a"), SimpleNamespace(name="b")], [SimpleNamespace(name="c")]]
		with (
			patch.object(ledger, "USAGE_PAGE_SIZE", 2, create=True),
			patch.object(ledger, "frappe") as frappe,
		):
			qb = frappe.qb
			qb.get_query.return_value.run.side_effect = pages
			self.assertEqual([row.name for row in ledger._usage(filters)], ["a", "b", "c"])
		self.assertEqual(
			[
				(call.kwargs["filters"], call.kwargs["order_by"], call.kwargs["limit"])
				for call in qb.get_query.call_args_list
			],
			[(filters, "name asc", 2), ({**filters, "name": [">", "b"]}, "name asc", 2)],
		)

	def test_purge_batch_breaks_timestamp_ties_by_name(self):
		with (
			patch.object(maintenance.policy, "require_user"),
			patch.object(maintenance, "frappe") as frappe,
			patch.object(maintenance, "now_datetime", return_value=datetime(2026, 1, 1)),
		):
			frappe.conf.get.return_value = maintenance.DEFAULT_RETENTION_DAYS
			frappe.qb.get_query.return_value.run.return_value = []
			maintenance.purge_usage()
			self.assertEqual(frappe.qb.get_query.call_args.kwargs["order_by"], "attempted_at asc, name asc")
