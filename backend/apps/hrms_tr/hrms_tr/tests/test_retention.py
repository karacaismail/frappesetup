"""Check that HRMS retention uses only the configured period and eligible records."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

import frappe

from hrms_tr import retention


class TestRetention(TestCase):
	def test_missing_or_invalid_period_never_reads_or_deletes_records(self):
		for value in (None, False, True, "30", 0, -1, 1.5):
			with (
				self.subTest(value=value),
				patch.object(retention, "_", side_effect=lambda message: message),
				patch.object(retention, "frappe") as framework,
			):
				framework.conf = {"hrms_tr_retention_days": value}
				framework.ValidationError = frappe.ValidationError
				framework.throw.side_effect = frappe.ValidationError
				with self.assertRaises(frappe.ValidationError):
					retention.purge(dry_run=False)
				framework.get_all.assert_not_called()
				framework.delete_doc.assert_not_called()

	def test_default_preview_uses_configured_cutoff_and_does_not_write(self):
		with (
			patch.object(retention, "frappe") as framework,
			patch.object(retention, "today", return_value="2026-11-22"),
		):
			framework.conf = {"hrms_tr_retention_days": 30}
			framework.get_all.return_value = ["EMP-LEFT"]
			framework.qb.get_query.return_value.run.return_value = [{"name": "LEAVE-1"}]
			framework.get_doc.side_effect = [
				SimpleNamespace(status="Left", relieving_date="2026-10-01"),
				SimpleNamespace(employee="EMP-LEFT", to_date="2026-10-02", docstatus=0),
			]
			result = retention.purge()
			self.assertEqual(result, {"dry_run": True, "cutoff": "2026-10-23", "employees": 1, "leaves": 1})
			self.assertEqual(framework.get_all.call_args_list[0].kwargs["filters"]["status"], "Left")
			self.assertEqual(
				framework.get_all.call_args_list[0].kwargs["filters"]["relieving_date"], ["<", "2026-10-23"]
			)
			framework.delete_doc.assert_not_called()

	def test_purge_deletes_only_expired_leave_records_permanently(self):
		with (
			patch.object(retention, "frappe") as framework,
			patch.object(retention, "today", return_value="2026-11-22"),
		):
			framework.conf = {"hrms_tr_retention_days": 30}
			framework.get_all.return_value = ["EMP-ACTIVE", "EMP-LEFT"]
			framework.qb.get_query.return_value.run.return_value = [{"name": "LEAVE-1"}]
			leave = Mock(employee="EMP-LEFT", to_date="2026-10-02", docstatus=0)
			leave.name = "LEAVE-1"
			framework.get_doc.side_effect = [
				SimpleNamespace(status="Active", relieving_date="2026-10-01"),
				SimpleNamespace(status="Left", relieving_date="2026-10-01"),
				leave,
			]
			result = retention.purge(dry_run=False)
			self.assertEqual((result["employees"], result["leaves"]), (1, 1))
			framework.only_for.assert_called_once_with("System Manager")
			leave.cancel.assert_not_called()
			self.assertEqual(
				framework.delete_doc.call_args_list,
				[
					call("Leave Application", "LEAVE-1", delete_permanently=True),
				],
			)
			self.assertTrue(all(entry.kwargs["for_update"] for entry in framework.get_doc.call_args_list))
			self.assertTrue(framework.qb.get_query.call_args.kwargs["for_update"])
			framework.db.commit.assert_not_called()
