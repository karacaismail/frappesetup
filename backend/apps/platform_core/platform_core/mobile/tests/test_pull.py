import unittest
from dataclasses import dataclass
from unittest.mock import Mock

from platform_core.mobile.service import pull

SCOPE = ("site", "account", "installation", "mobile")
SECRET = b"a" * 32


@dataclass(frozen=True)
class Event:
	sequence: int
	record_type: str
	record_id: str


class Store:
	retention_floor = 0
	pending_events = False

	def __init__(self):
		self.events = [Event(i, "sample", str(i)) for i in range(1, 4)]
		self.records = {
			event.record_id: {"version": "v1", "fields": {"title": "Example"}} for event in self.events
		}
		self.deliveries = {}
		self.last_audit = None
		self.reconcile_deliveries = Mock(return_value=None)

	@property
	def sequence(self):
		return self.events[-1].sequence if self.events else self.retention_floor

	def audit_due(self, installation, now):
		return self.last_audit is None or now - self.last_audit >= 300

	def finish_audit(self, installation, now):
		self.last_audit = now

	def read_events(self, installation, after, ceiling, limit):
		return [event for event in self.events if after < event.sequence <= ceiling][:limit]

	def may_have_delivered(self, installation, record_type, record_id):
		return (record_type, record_id) in self.deliveries

	def record_delivery(self, installation, record_type, record_id):
		self.deliveries[record_type, record_id] = True


class PullTest(unittest.TestCase):
	def setUp(self):
		self.store = Store()
		self.projections = {"sample": lambda account, record_id: self.store.records.get(record_id)}

	def scan(self, account, after, limit):
		return sorted(record_id for record_id in self.store.records if after is None or record_id > after)[
			:limit
		]

	def page(self, cursor=None, limit=100, now=100):
		return pull(
			self.store,
			self.projections,
			SECRET,
			SCOPE,
			cursor,
			limit,
			account="account",
			now=now,
			inventories={"sample": self.scan},
		)

	def test_first_copy_finishes_before_subsequent_changes(self):
		first = self.page(limit=2)
		self.assertTrue(first["has_more"])
		self.store.records["0"] = {"version": "v1", "fields": {}}
		self.store.events.append(Event(4, "sample", "0"))
		last = self.page(first["cursor"], limit=2)
		self.assertEqual([change["record_id"] for change in last["changes"]], ["3"])
		next_page = self.page(last["cursor"])
		self.assertEqual([change["record_id"] for change in next_page["changes"]], ["0"])

	def test_permission_loss_is_retryable_and_does_not_expose_record_fields(self):
		first = self.page()
		del self.store.records["1"]
		self.store.events.append(Event(4, "sample", "1"))
		lost = self.page(first["cursor"])
		self.assertEqual(lost["changes"], [{"record_type": "sample", "record_id": "1", "kind": "remove"}])
		self.assertEqual(self.page(first["cursor"])["changes"], lost["changes"])

	def test_undelivered_record_does_not_expose_existence(self):
		del self.store.records["1"]
		self.assertEqual([change["record_id"] for change in self.page()["changes"]], ["2", "3"])

	def test_empty_filtered_page_still_advances_cursor(self):
		self.projections["sample"] = lambda account, record_id: None
		first = self.page(limit=1)
		self.assertEqual(first["changes"], [])
		self.assertTrue(first["has_more"])
		last = self.page(first["cursor"])
		self.assertFalse(last["has_more"])
		self.assertNotEqual(first["cursor"], last["cursor"])

	def test_delivery_audit_continues_and_waits_to_restart(self):
		initial = self.page()
		checkpoint = "a" * 64
		self.store.reconcile_deliveries.side_effect = [checkpoint, None, None]
		page = self.page(initial["cursor"])
		self.assertTrue(page["has_more"])
		page = self.page(page["cursor"])
		self.assertFalse(page["has_more"])
		self.store.reconcile_deliveries.assert_called_with(
			self.projections, "installation", "account", checkpoint
		)
		page = self.page(page["cursor"], now=399)
		self.assertFalse(page["has_more"])
		self.assertEqual(self.store.reconcile_deliveries.call_count, 2)
		self.page(page["cursor"], now=400)
		self.assertEqual(self.store.reconcile_deliveries.call_count, 3)

	def test_full_copy_works_after_history_is_pruned(self):
		self.store.events.clear()
		self.store.retention_floor = 3
		page = self.page()
		self.assertEqual([change["record_id"] for change in page["changes"]], ["1", "2", "3"])
		self.assertEqual(self.page(page["cursor"])["changes"], [])

	def test_a_visibility_grant_event_delivers_a_previously_unseen_record(self):
		previously_hidden = self.store.records.pop("1")
		initial = self.page()
		self.assertNotIn("1", [change["record_id"] for change in initial["changes"]])
		self.store.records["1"] = previously_hidden
		self.store.events.append(Event(self.store.sequence + 1, "sample", "1"))
		next_page = self.page(initial["cursor"])
		self.assertEqual([change["record_id"] for change in next_page["changes"]], ["1"])
