"""Regression coverage for mobile metadata and the Frappe store."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

try:
	import frappe
	from frappe.tests import IntegrationTestCase
except ModuleNotFoundError as exc:
	if exc.name != "frappe":
		raise
	frappe = None
else:
	from platform_core.mobil import store as storage

if frappe is not None:

	class TestMobileStore(TestCase):
		def test_store_reads_sequence_without_acquiring_the_site_lock(self):
			db = Mock()
			db.get_value.return_value = SimpleNamespace(sequence=1, retention_floor=0)
			with patch.object(storage.frappe, "db", db):
				store = storage.MobileStore()
			self.assertEqual(store.sequence, 1)
			self.assertFalse(db.get_value.call_args.kwargs.get("for_update", False))

		def test_redelivery_restores_visibility_in_the_existing_row(self):
			db = Mock()
			db.get_value.side_effect = [
				SimpleNamespace(sequence=1, retention_floor=0),
				SimpleNamespace(name="existing-delivery", visible=0),
			]
			with patch.object(storage.frappe, "db", db):
				storage.MobileStore().record_delivery("installation", "type", "record")
			db.set_value.assert_called_once_with("Mobile Delivery", "existing-delivery", "visible", 1)

		def test_user_cleanup_removes_mobile_metadata(self):
			db = Mock()
			with (
				patch.object(storage.frappe, "db", db),
				patch.object(storage, "_select", return_value=[SimpleNamespace(name="installation")]),
			):
				storage.delete_user_state(SimpleNamespace(name="account"))
			self.assertEqual(
				[(c.args[0], c.args[1]) for c in db.delete.call_args_list],
				[
					("Mobile Account State", {"account": "account"}),
					("Mobile Change", {"target_installation": ["in", ["installation"]]}),
					("Mobile Delivery", {"installation_id": ["in", ["installation"]]}),
					("Mobile Installation", {"name": ["in", ["installation"]]}),
				],
			)

	class TestMobileStoreIntegration(IntegrationTestCase):
		def make_installation(self, account):
			identity = SimpleNamespace(account=account, scope="test", principal="test-principal")
			installation = str(uuid4())
			storage.MobileStore().install(identity, installation)
			return installation

		def test_second_access_loss_emits_a_new_targeted_removal(self):
			installation = self.make_installation("Administrator")
			store = storage.MobileStore()
			record_type, record_id = "fixture", str(uuid4())
			store.record_delivery(installation, record_type, record_id)
			store.reconcile_deliveries({}, installation, "Administrator", None)
			first = store.sequence

			store.record_delivery(installation, record_type, record_id)
			store.reconcile_deliveries({}, installation, "Administrator", None)
			second = store.sequence

			self.assertGreater(second, first)
			rows = frappe.get_all(
				"Mobile Change",
				filters={"target_installation": installation, "record_id": record_id, "kind": "remove"},
				pluck="sequence",
				order_by="sequence",
			)
			self.assertEqual(rows, [first, second])

		def test_user_deletion_removes_installation_delivery_and_targeted_change(self):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": f"mobile-{uuid4().hex}@example.test",
					"first_name": "Test",
					"send_welcome_email": 0,
				}
			).insert()
			storage._insert("Mobile Account State", account=user.name, revoked_through="0")
			installation = self.make_installation(user.name)
			other_installation = self.make_installation("Administrator")
			store = storage.MobileStore()
			record_id = str(uuid4())
			store.record_delivery(installation, "fixture", record_id)
			store.record_delivery(other_installation, "fixture", record_id)
			store.append_change("fixture", record_id, "remove", target_installation=installation)
			store.append_change("fixture", record_id, "remove", target_installation=other_installation)

			frappe.delete_doc("User", user.name)

			self.assertFalse(frappe.db.exists("Mobile Account State", {"account": user.name}))
			self.assertFalse(frappe.db.exists("Mobile Installation", installation))
			self.assertFalse(frappe.db.exists("Mobile Delivery", {"installation_id": installation}))
			self.assertFalse(frappe.db.exists("Mobile Change", {"target_installation": installation}))
			self.assertTrue(frappe.db.exists("Mobile Installation", other_installation))
			self.assertTrue(frappe.db.exists("Mobile Delivery", {"installation_id": other_installation}))
			self.assertTrue(frappe.db.exists("Mobile Change", {"target_installation": other_installation}))
