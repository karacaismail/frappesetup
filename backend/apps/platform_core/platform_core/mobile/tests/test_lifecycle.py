"""Regression tests for account revocation and manual retention."""

import time
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

try:
	import frappe
	from frappe.tests import IntegrationTestCase
	from frappe.utils import now_datetime
except ModuleNotFoundError as error:
	if error.name != "frappe":
		raise
	raise unittest.SkipTest("Frappe is required for mobile lifecycle tests") from error


class MobileLifecycleTest(IntegrationTestCase):
	def setUp(self):
		suffix = uuid4().hex
		self.account = f"mobile-{suffix}@example.test"
		frappe.get_doc(
			{"doctype": "User", "email": self.account, "first_name": "Mobile Test", "send_welcome_email": 0}
		).insert()
		self.now = int(time.time())

	def identity(self, issued_at):
		return SimpleNamespace(
			site=frappe.local.site,
			account=self.account,
			principal="a" * 64,
			scope="mobile",
			issued_at=issued_at,
		)

	def test_first_account_state_checks_current_user_before_inserting(self):
		from platform_core.mobile import lifecycle
		from platform_core.mobile.protocol import MobileError

		def enabled_snapshot(doctype, name, field, *, for_update=False):
			self.assertEqual((doctype, name, field), ("User", self.account, "enabled"))
			return None if for_update else 1

		with (
			patch.object(lifecycle, "_account_state", return_value=None),
			patch.object(frappe.db, "get_value", side_effect=enabled_snapshot),
			patch.object(lifecycle, "insert_metadata") as insert,
		):
			with self.assertRaises(MobileError) as raised:
				lifecycle.lock_account(self.identity(self.now))
			self.assertEqual(raised.exception.code, "mobile_token_required")
			insert.assert_not_called()

	def test_revoke_blocks_new_installations_for_the_same_issued_token(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobile.protocol import MobileError

		first = {"installation_id": str(uuid4())}
		second = {"installation_id": str(uuid4())}
		old = self.identity(self.now - 1)
		with patch("platform_core.mobile.lifecycle.time.time", return_value=self.now):
			self.assertEqual(_register(old, first), first)
			old.installation = first["installation_id"]
			self.assertEqual(_revoke(old, first), {"revoked": 1})
			for issued_at in (None, self.now - 1, self.now, self.now + 30):
				with self.assertRaises(MobileError) as raised:
					_register(self.identity(issued_at), second)
				self.assertEqual(raised.exception.code, "mobile_token_revoked")
			self.assertEqual(_register(self.identity(self.now + 31), second), second)

	def test_pull_rejects_disabled_account_before_opening_cursor(self):
		from platform_core.api.mobile import _pull, _register
		from platform_core.mobile.protocol import MobileError

		identity = self.identity(self.now)
		body = {"installation_id": str(uuid4())}
		_register(identity, body)
		frappe.db.set_value("User", self.account, "enabled", 0)
		with self.assertRaises(MobileError) as raised:
			_pull(identity, body)
		self.assertEqual((raised.exception.code, raised.exception.status), ("mobile_token_required", 401))

	def test_installation_limit_leaves_existing_registration_idempotent(self):
		from platform_core.api.mobile import _register
		from platform_core.mobile.protocol import MobileError

		first = {"installation_id": str(uuid4())}
		identity = self.identity(self.now)
		with patch("platform_core.mobile.lifecycle.MAX_ACTIVE_INSTALLATIONS", new=1):
			self.assertEqual(_register(identity, first), first)
			self.assertEqual(_register(identity, first), first)
			with self.assertRaises(MobileError) as raised:
				_register(identity, {"installation_id": str(uuid4())})
			self.assertEqual(raised.exception.code, "installation_limit")

	def test_cleanup_preserves_recent_records_and_preview_has_no_effect(self):
		from platform_core.mobile.retention import cleanup
		from platform_core.mobile.store import MobileStore

		store = MobileStore()
		old, recent = uuid4().hex, uuid4().hex
		for key in (old, recent):
			store.remember_operation(key, "a" * 64, {"status": "applied"})
		for record_id in (old, recent):
			store.append_change("test", record_id, "upsert")
		old_event = frappe.db.get_value(
			"PLT Mobile Change", {"record_id": old}, ["name", "sequence"], as_dict=True
		)
		for doctype, name in (("PLT Mobile Operation", old), ("PLT Mobile Change", old_event.name)):
			frappe.db.set_value(doctype, name, "creation", now_datetime() - timedelta(days=2))

		with patch.dict(
			frappe.conf, {"mobile_operation_retention_days": 1, "mobile_upsert_retention_days": 1}
		):
			preview = cleanup(dry_run=True)
			self.assertGreaterEqual(preview["eligible_changes"], 1)
			self.assertGreaterEqual(preview["eligible_operations"], 1)
			self.assertEqual(preview["removed"], 0)
			self.assertTrue(frappe.db.exists("PLT Mobile Operation", old))
			self.assertTrue(frappe.db.exists("PLT Mobile Change", old_event.name))

			result = cleanup()
			self.assertGreaterEqual(result["removed"], 1)
			self.assertGreaterEqual(result["operations_removed"], 1)
			self.assertFalse(frappe.db.exists("PLT Mobile Operation", old))
			self.assertTrue(frappe.db.exists("PLT Mobile Operation", recent))
			self.assertTrue(frappe.db.exists("PLT Mobile Change", {"record_id": recent}))
			self.assertGreaterEqual(MobileStore().retention_floor, old_event.sequence)
