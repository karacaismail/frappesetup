"""Check the retention command's validation, preview and bounded writes."""

from unittest import TestCase
from unittest.mock import call, patch

import frappe
from pypika import Table

from hrms_tr import retention


class TestRetention(TestCase):
	def test_invalid_input_never_reads_or_deletes_records(self):
		for days, limit in ((None, 500), (True, 500), ("30", 500), (0, 500), (30, True), (30, 0)):
			with (
				self.subTest(days=days, limit=limit),
				patch.object(retention, "_", side_effect=lambda message: message),
				patch.object(retention, "frappe") as framework,
			):
				framework.conf = {"hrms_tr_retention_days": days}
				framework.ValidationError = frappe.ValidationError
				framework.throw.side_effect = frappe.ValidationError
				with self.assertRaises(frappe.ValidationError):
					retention.purge(dry_run=False, limit=limit)
				framework.qb.from_.assert_not_called()
				framework.delete_doc.assert_not_called()

	def test_default_preview_limits_result_without_writes(self):
		with (
			patch.object(retention, "frappe") as framework,
			patch.object(retention, "today", return_value="2026-11-22"),
		):
			framework.conf = {"hrms_tr_retention_days": 30}
			framework.qb.DocType.side_effect = Table

			query = framework.qb.from_.return_value.join.return_value.on.return_value.where.return_value
			query.select.return_value.run.return_value = [(501,)]
			self.assertEqual(
				retention.purge(), {"dry_run": True, "cutoff": "2026-10-23", "leaves": 500, "remaining": 1}
			)
			framework.delete_doc.assert_not_called()

	def test_batch_only_deletes_exact_leave_names_without_cancellation(self):
		with (
			patch.object(retention, "frappe") as framework,
			patch.object(retention, "today", return_value="2026-11-22"),
		):
			framework.conf = {"hrms_tr_retention_days": 30}
			framework.qb.DocType.side_effect = Table

			query = framework.qb.from_.return_value.join.return_value.on.return_value.where.return_value
			query.select.return_value.run.return_value = [(2,)]
			batch = query.select.return_value.orderby.return_value.limit
			batch.return_value.for_update.return_value.run.return_value = [("LEAVE-1",)]
			purge_outcome = retention.purge(dry_run=False, limit=1)
			self.assertEqual((purge_outcome["leaves"], purge_outcome["remaining"]), (1, 1))
			batch.assert_called_once_with(1)
			framework.only_for.assert_called_once_with("System Manager")
			self.assertEqual(
				framework.delete_doc.call_args_list,
				[call("Leave Application", "LEAVE-1", delete_permanently=True)],
			)
			framework.get_doc.assert_not_called()
			framework.db.commit.assert_not_called()
