import unittest

from platform_core.mobil.protocol import Command, MobileError
from platform_core.mobil.service import push

OPERATION = "12d67d64-a312-43d2-9afb-2eb7412561de"
RECORD = "5cc4515b-c67f-4ca9-8706-7768158f4df2"


class SampleCommand:
	declaration = Command("update", frozenset({"title"}))
	record_type = "sample"

	def __init__(self):
		self.current = {
			"kind": "upsert",
			"record_type": self.record_type,
			"record_id": RECORD,
			"version": "1",
		}
		self.effects = 0
		self.allowed = True

	def authorize(self, account, record_id):
		if not self.allowed:
			raise MobileError("record_forbidden", 403)

	def read_locked(self, account, record_id):
		return self.current

	def apply(self, account, record_id, fields):
		self.effects += 1
		self.current = dict(self.current, version="2")


class Transaction:
	def __init__(self):
		self.operations = {}
		self.changes = []

	def get_operation(self, key):
		return self.operations.get(key)

	def remember_operation(self, key, digest, result):
		self.operations[key] = (digest, result)

	def append_change(self, record_type, record_id, kind):
		self.changes.append((record_type, record_id, kind))


class PushTest(unittest.TestCase):
	def setUp(self):
		self.command = SampleCommand()
		self.store = Transaction()
		self.operation = {
			"command": "sample.update",
			"operation_id": OPERATION,
			"record_id": RECORD,
			"version": "1",
			"fields": {"title": "Sample"},
		}

	def submit(self, operation=None):
		return push(
			self.store,
			{"sample.update": self.command},
			"site",
			"account",
			[operation or self.operation],
			principal="principal",
		)

	def test_retry_returns_first_result_and_does_not_write_again(self):
		result = self.submit()
		self.assertEqual(self.submit(), result)
		self.assertEqual(self.command.effects, 1)
		self.assertEqual(self.store.changes, [("sample", RECORD, "upsert")])

	def test_same_operation_id_with_different_content_cannot_write(self):
		self.submit()
		with self.assertRaises(MobileError) as error:
			self.submit(dict(self.operation, fields={"title": "Other"}))
		self.assertEqual((error.exception.status, error.exception.code), (409, "operation_conflict"))
		self.assertEqual(self.command.effects, 1)

	def test_stale_version_returns_projected_current_record_without_writing(self):
		with self.assertRaises(MobileError) as error:
			self.submit(dict(self.operation, version="0"))
		self.assertEqual(error.exception.current, self.command.current)
		self.assertEqual(error.exception.status, 409)
		self.assertEqual(self.store.operations, {})
		self.assertEqual(self.store.changes, [])

	def test_replay_returns_only_acknowledgment_after_record_access_changes(self):
		result = self.submit()
		self.command.allowed = False
		self.assertEqual(self.submit(), result)
		self.assertEqual(result, {"operations": [{"operation_id": OPERATION, "status": "applied"}]})

	def test_rejects_invalid_batch_before_writing(self):
		with self.assertRaises(MobileError):
			push(
				self.store,
				{"sample.update": self.command},
				"site",
				"account",
				[self.operation, {}],
				principal="principal",
			)
		self.assertEqual(self.command.effects, 0)
