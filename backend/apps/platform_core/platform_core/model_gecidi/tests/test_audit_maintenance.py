"""Regression tests for recoverable retention and stalled reservations."""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from platform_core import hooks
from platform_core.api import model
from platform_core.model_gecidi import api, gateway, ledger, maintenance, management_tools, policy


class PreviewRequiredTests(unittest.TestCase):
	def test_public_purge_previews_without_writes(self):
		with (
			patch.object(maintenance, "frappe") as framework,
			patch.object(policy, "require_user"),
			patch.object(maintenance, "now_datetime", return_value=datetime(2026, 1, 1)),
		):
			framework.get_roles.return_value = ["System Manager"]
			framework.db.count.return_value = 3
			framework.qb.get_query.return_value.run.return_value = [SimpleNamespace(name="approved")]
			self.assertEqual(
				api.purge_usage_logs(dry_run=True), {"eligible": 3, "deleted": 0, "names": ["approved"]}
			)
			framework.delete_doc.assert_not_called()
			framework.get_doc.assert_not_called()
			self.assertEqual(framework.cache.mock_calls, [])

	def test_public_purge_propagates_deadlock_after_database_aborts_transaction(self):
		with (
			patch.object(policy, "require_user"),
			patch.object(frappe, "get_roles", return_value=["System Manager"]),
			patch.object(frappe.local, "db", Mock(), create=True) as database,
			patch.object(maintenance, "now_datetime", return_value=datetime(2026, 1, 1)),
			patch.object(maintenance, "_purge_batch", side_effect=frappe.QueryDeadlockError),
		):
			database.after_commit = frappe.utils.CallbackManager()

			def rollback(**kwargs):
				if kwargs:
					raise RuntimeError("Savepoint no longer exists")

			database.rollback.side_effect = rollback
			with self.assertRaises(frappe.QueryDeadlockError):
				api.purge_usage_logs(names=["approved"])
			database.rollback.assert_called_once_with()

	def test_public_purge_rejects_an_ai_manager(self):
		with (
			patch.object(policy, "require_user"),
			patch.object(frappe, "get_roles", return_value=["AI Manager"]),
		):
			with self.assertRaises(frappe.PermissionError):
				api.purge_usage_logs()

	def test_delete_rejects_missing_preview_before_querying_records(self):
		with (
			patch.object(maintenance, "frappe") as framework,
			patch.object(policy, "require_user"),
			patch.object(maintenance, "now_datetime", return_value=datetime(2026, 1, 1)),
		):
			framework.get_roles.return_value = ["System Manager"]
			with self.assertRaises(policy.Denied) as caught:
				maintenance.purge_usage(dry_run=False)
			self.assertEqual((caught.exception.status, caught.exception.code), (400, "preview_required"))
			self.assertFalse(framework.db.count.called)

	def test_stale_recovery_is_registered_for_http_and_ai_approval(self):
		self.assertIn("platform_core.model_gecidi.management_tools.declare", hooks.ai_tools)
		self.assertIn(model.reconcile_stale_pending, frappe.whitelisted)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[model.reconcile_stale_pending], ["POST"]
		)
		tool = next(item for item in management_tools.declare() if item["name"] == "reconcile_stale_pending")
		self.assertEqual(
			(tool["kind"], tool["versioned"], tool["roles"]),
			(
				"write",
				True,
				sorted(policy.MANAGERS),
			),
		)
		self.assertTrue(tool["preview"])

	def test_retention_uses_permanent_delete(self):
		now = datetime(2026, 1, 1)
		with (
			patch.object(maintenance, "frappe") as framework,
			patch.object(policy, "require_user"),
			patch.object(maintenance, "now_datetime", return_value=now),
		):
			framework.session.user = "Manager A"
			framework.get_roles.return_value = ["System Manager"]
			framework.db.count.return_value = 0
			framework.cache.get_value.return_value = {
				"user": "Manager A",
				"days": 365,
				"cutoff": now - timedelta(days=365),
				"batch": [("retention-fixture", now)],
			}
			framework.qb.get_query.return_value.run.return_value = [
				SimpleNamespace(name="retention-fixture", modified=now)
			]
			maintenance.purge_usage(dry_run=False, preview_token="a" * 64)
			self.assertIs(framework.delete_doc.call_args.kwargs.get("delete_permanently"), True)

	def test_foreign_preview_rejects_before_querying_records(self):
		with patch.object(maintenance, "frappe") as framework, patch.object(policy, "require_user"):
			framework.session.user = "Manager B"
			framework.get_roles.return_value = ["System Manager"]
			framework.cache.get_value.return_value = {"user": "Manager A"}
			with self.assertRaises(policy.Denied) as caught:
				maintenance.purge_usage(dry_run=False, preview_token="a" * 64)
			self.assertEqual((caught.exception.status, caught.exception.code), (409, "preview_invalid"))
			self.assertFalse(framework.qb.get_query.called)

	def test_already_claimed_empty_batch_cannot_write_a_second_audit_record(self):
		now = datetime(2026, 1, 1)
		with (
			patch.object(maintenance, "frappe") as framework,
			patch.object(policy, "require_user"),
			patch.object(maintenance, "now_datetime", return_value=now),
		):
			framework.session.user = "Manager A"
			framework.get_roles.return_value = ["System Manager"]
			framework.cache.get_value.return_value = {
				"user": "Manager A",
				"days": 365,
				"cutoff": now - timedelta(days=365),
				"batch": [],
			}
			framework.qb.get_query.return_value.run.return_value = []
			framework.cache.getdel.return_value = None
			with self.assertRaises(policy.Denied) as caught:
				maintenance.purge_usage(dry_run=False, preview_token="a" * 64)
			self.assertEqual((caught.exception.status, caught.exception.code), (409, "preview_invalid"))
			self.assertFalse(framework.get_doc.called)

	def test_missing_usage_log_uses_native_permission_error(self):
		with patch.object(frappe, "get_doc", side_effect=frappe.DoesNotExistError):
			with self.assertRaises(frappe.PermissionError):
				maintenance._usage_log("missing")

	def test_pending_and_terminal_states_are_each_committed(self):
		"""Record the two transaction boundaries independently of the provider."""
		db = Mock()
		with patch.object(ledger, "frappe") as framework, patch.object(ledger, "now_datetime"):
			framework.attach_mock(db, "db")
			record = framework.get_doc.return_value
			record.name = "reservation"
			framework.attach_mock(record, "usage_log")
			api = account = provider = model = SimpleNamespace(name="id", cost_currency="USD", prices_known=0)
			name = ledger.begin(None, api, account, provider, model, cost=Decimal("0.125"), tokens=10)
			self.assertEqual(framework.get_doc.call_args.args[0]["result"], "pending")
			ledger.finish(name, model, "unknown", 1)
		self.assertEqual(framework.mock_calls[1:3], [call.usage_log.db_insert(), call.db.commit()])
		self.assertEqual(db.set_value.call_args.args[1], {"name": name, "result": "pending"})
		self.assertEqual(db.set_value.call_args.args[2]["result"], "unknown")
		self.assertEqual(framework.mock_calls[-1], call.db.commit())


class TestUsageMaintenance(IntegrationTestCase):
	def test_public_purge_uses_fixed_retention_and_returns_counts(self):
		now = now_datetime()
		old = self._usage("success", now - timedelta(days=366))
		recent = self._usage("success", now - timedelta(days=364))
		pending = self._usage("pending", now - timedelta(days=366))
		with patch.dict(frappe.conf, {"model_gateway_usage_retention_days": 36500}):
			self.assertEqual(
				api.purge_usage_logs(dry_run=True), {"eligible": 1, "deleted": 0, "names": [old.name]}
			)
			self.assertTrue(frappe.db.exists("AI Usage Log", old.name))
			self.assertEqual(
				api.purge_usage_logs(names=[old.name]), {"eligible": 1, "deleted": 1, "names": [old.name]}
			)
		self.assertFalse(frappe.db.exists("AI Usage Log", old.name))
		self.assertTrue(frappe.db.exists("AI Usage Log", recent.name))
		self.assertTrue(frappe.db.exists("AI Usage Log", pending.name))
		self.assertFalse(
			frappe.db.exists(
				"Deleted Document",
				{"deleted_doctype": "AI Usage Log", "deleted_name": old.name},
			)
		)

	def test_public_purge_leaves_newly_eligible_record_outside_approval(self):
		now = now_datetime()
		approved = self._usage("success", now - timedelta(days=366))
		later = self._usage("success", now - timedelta(days=364))
		with patch.object(maintenance, "now_datetime", return_value=now):
			preview = api.purge_usage_logs(dry_run=True)
		self.assertEqual(preview["names"], [approved.name])
		with patch.object(maintenance, "now_datetime", return_value=now + timedelta(days=2)):
			result = api.purge_usage_logs(names=preview["names"])
		self.assertEqual(result["names"], [approved.name])
		self.assertEqual(result["deleted"], 1)
		self.assertTrue(frappe.db.exists("AI Usage Log", later.name))

	def test_public_purge_rejects_entire_batch_when_a_record_becomes_ineligible(self):
		now = now_datetime()
		first = self._usage("success", now - timedelta(days=367))
		second = self._usage("success", now - timedelta(days=366))
		preview = api.purge_usage_logs(dry_run=True)
		frappe.db.set_value("AI Usage Log", second.name, "result", "unknown")
		with self.assertRaises(frappe.ValidationError):
			api.purge_usage_logs(names=preview["names"])
		self.assertTrue(frappe.db.exists("AI Usage Log", first.name))
		self.assertEqual(frappe.db.get_value("AI Usage Log", second.name, "result"), "unknown")

	def test_public_purge_rolls_back_first_delete_if_second_fails(self):
		now = now_datetime()
		first = self._usage("success", now - timedelta(days=367))
		second = self._usage("success", now - timedelta(days=366))
		preview = api.purge_usage_logs(dry_run=True)
		delete_doc = frappe.delete_doc
		commit_callbacks = len(frappe.db.after_commit)

		def fail_on_second(doctype, name, **kwargs):
			if name == second.name:
				self.assertFalse(frappe.db.exists("AI Usage Log", first.name))
				raise frappe.ValidationError("Second deletion failed")
			frappe.db.after_commit.add(lambda: None)
			return delete_doc(doctype, name, **kwargs)

		with (
			patch.object(frappe, "delete_doc", side_effect=fail_on_second),
			self.assertRaisesRegex(frappe.ValidationError, "Second deletion failed"),
		):
			api.purge_usage_logs(names=preview["names"])

		self.assertEqual(len(frappe.db.after_commit), commit_callbacks)
		for record in (first, second):
			self.assertTrue(frappe.db.exists("AI Usage Log", record.name))

	def _usage(self, outcome, attempted_at):
		suffix = uuid4().hex
		provider = frappe.get_doc(
			doctype="AI Provider", provider_name=f"Retention fixture {suffix}", adapter="openai"
		).insert()
		account = frappe.get_doc(
			doctype="AI Account",
			account_name=f"Retention fixture {suffix}",
			provider=provider.name,
			currency="USD",
		).insert()
		api = frappe.get_doc(
			doctype="AI API",
			account=account.name,
			api_name=f"Retention fixture {suffix}",
			base_url="https://fixture.example.test/",
			auth_type="none",
		).insert()
		model = frappe.get_doc(
			doctype="AI Model",
			provider=provider.name,
			model_id=f"retention-fixture-{suffix}",
			context_size=1024,
		).insert()
		log = frappe.get_doc(
			doctype="AI Usage Log",
			name=str(uuid4()),
			attempted_at=attempted_at,
			user="Administrator",
			provider=provider.name,
			account=account.name,
			api=api.name,
			model=model.name,
			currency="USD",
			duration_ms=0,
			result=outcome,
			reserved_tokens=10,
			reservation_known=1,
			reserved_cost=Decimal("0.125"),
		).insert()
		self.addCleanup(frappe.db.delete, "AI Usage Log", {"name": log.name})
		return log

	def test_confirmed_purge_leaves_no_deleted_document_copy(self):
		old = now_datetime() - timedelta(days=366)
		log = self._usage("success", old)
		preview = maintenance.purge_usage()
		self.assertIn(log.name, preview["targets"])
		self.assertTrue(frappe.db.exists("AI Usage Log", log.name))
		execution = maintenance.purge_usage(dry_run=False, preview_token=preview["preview_token"])
		self.assertIn(log.name, execution["targets"])
		self.assertFalse(frappe.db.exists("AI Usage Log", log.name))
		deleted = frappe.db.get_value(
			"Deleted Document", {"deleted_doctype": "AI Usage Log", "deleted_name": log.name}, "name"
		)
		self.assertIsNone(deleted)
		with self.assertRaises(policy.Denied) as replay:
			maintenance.purge_usage(dry_run=False, preview_token=preview["preview_token"])
		self.assertEqual(replay.exception.code, "preview_invalid")

	def test_purge_rejects_a_changed_batch_without_deleting_other_rows(self):
		old = now_datetime() - timedelta(days=366)
		changed, other = [self._usage("success", old) for _sample_index in range(2)]
		preview = maintenance.purge_usage()
		frappe.db.set_value("AI Usage Log", changed.name, "result", "unknown")
		with self.assertRaises(policy.Denied) as caught:
			maintenance.purge_usage(dry_run=False, preview_token=preview["preview_token"])
		self.assertEqual(caught.exception.code, "preview_invalid")
		self.assertTrue(frappe.db.exists("AI Usage Log", other.name))

	def test_manual_recovery_closes_only_stale_pending_rows_and_keeps_reservations(self):
		now = now_datetime()
		stale = self._usage("pending", now - timedelta(seconds=gateway.STALE_ATTEMPT_SECONDS + 5))
		live = self._usage("pending", now)
		complete = self._usage("success", now - timedelta(seconds=gateway.STALE_ATTEMPT_SECONDS + 5))
		result = maintenance.reconcile_stale_pending()
		self.assertIn(stale.name, result["targets"])
		self.assertNotIn(live.name, result["targets"])
		self.assertNotIn(complete.name, result["targets"])
		stale.reload()
		self.assertEqual((stale.result, stale.cost_known, stale.reservation_known), ("unknown", 0, 1))
		self.assertEqual(stale.reserved_cost, 0.125)
		self.assertNotIn(stale.name, maintenance.reconcile_stale_pending()["targets"])

	def test_ai_recovery_changes_only_the_named_reservation(self):
		attempted = now_datetime() - timedelta(seconds=gateway.STALE_ATTEMPT_SECONDS + 5)
		first, second = [self._usage("pending", attempted) for _sample_index in range(2)]
		preview = management_tools.preview_reconcile_pending(name=first.name)
		self.assertEqual(preview["target_name"], first.name)
		self.assertEqual(preview["target_version"], str(first.modified))
		self.assertEqual(
			management_tools.reconcile_pending(name=first.name), {"closed": 1, "targets": [first.name]}
		)
		second.reload()
		self.assertEqual(second.result, "pending")
