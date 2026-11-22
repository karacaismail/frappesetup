import unittest
from dataclasses import dataclass

from platform_core.mobil.service import pull

SCOPE = ("site", "account", "installation", "mobile")
SECRET = b"a" * 32


@dataclass(frozen=True)
class Event:
	sequence: int
	record_type: str
	record_id: str


class Store:
	retention_floor = 0
	audit_size = 100

	def __init__(self):
		self.events = [Event(i, "sample", str(i)) for i in range(1, 4)]
		self.records = {
			event.record_id: {"version": "v1", "fields": {"title": "Example"}} for event in self.events
		}
		self.deliveries = {}

	@property
	def sequence(self):
		return len(self.events)

	def reconcile_deliveries(self, projections, installation, account, after):
		from platform_core.mobil.protocol import content_digest

		rows = sorted((content_digest(key), key) for key in self.deliveries)
		remaining = [row for row in rows if after is None or row[0] > after]
		for _, (record_type, record_id) in remaining[: self.audit_size]:
			key = (record_type, record_id)
			visible = record_type in projections and projections[record_type](account, record_id) is not None
			if self.deliveries[key] != visible:
				self.events.append(Event(self.sequence + 1, record_type, record_id))
				self.deliveries[key] = visible
		if len(remaining) > self.audit_size:
			return remaining[self.audit_size - 1][0]
		return None

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

	def page(self, cursor=None, limit=100):
		return pull(self.store, self.projections, SECRET, SCOPE, cursor, limit, account="account", now=100)

	def test_first_copy_finishes_before_subsequent_changes(self):
		first = self.page(limit=2)
		self.assertTrue(first["has_more"])
		self.store.records["4"] = {"version": "v1", "fields": {}}
		self.store.events.append(Event(4, "sample", "4"))
		last = self.page(first["cursor"], limit=2)
		self.assertEqual([change["record_id"] for change in last["changes"]], ["3"])
		next_page = self.page(last["cursor"])
		self.assertEqual([change["record_id"] for change in next_page["changes"]], ["4"])

	def test_permission_loss_is_retryable_and_does_not_expose_record_fields(self):
		first = self.page()
		del self.store.records["1"]
		lost = self.page(first["cursor"])
		self.assertEqual(lost["changes"], [{"record_type": "sample", "record_id": "1", "kind": "remove"}])
		self.assertEqual(self.page(first["cursor"]), lost)

	def test_undelivered_record_does_not_expose_existence(self):
		del self.store.records["1"]
		self.assertEqual([change["record_id"] for change in self.page()["changes"]], ["2", "3"])

	def test_empty_filtered_page_still_advances_cursor(self):
		self.store.records.clear()
		first = self.page(limit=1)
		self.assertEqual(first["changes"], [])
		self.assertTrue(first["has_more"])
		last = self.page(first["cursor"])
		self.assertFalse(last["has_more"])
		self.assertNotEqual(first["cursor"], last["cursor"])

	def test_delivery_audit_is_bounded_and_eventually_reports_every_removal(self):
		self.store.audit_size = 1
		initial = self.page()
		self.store.records.clear()
		page = self.page(initial["cursor"])
		removed = [change["record_id"] for change in page["changes"]]
		self.assertTrue(page["has_more"])
		self.assertEqual(len(removed), 1)
		for _ in range(2):
			page = self.page(page["cursor"])
			removed.extend(change["record_id"] for change in page["changes"])
		self.assertFalse(page["has_more"])
		self.assertCountEqual(removed, ["1", "2", "3"])

	def test_a_visibility_grant_event_delivers_a_previously_unseen_record(self):
		previously_hidden = self.store.records.pop("1")
		initial = self.page()
		self.assertNotIn("1", [change["record_id"] for change in initial["changes"]])
		self.store.records["1"] = previously_hidden
		self.store.events.append(Event(self.store.sequence + 1, "sample", "1"))
		next_page = self.page(initial["cursor"])
		self.assertEqual([change["record_id"] for change in next_page["changes"]], ["1"])
