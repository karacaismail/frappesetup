import base64
import unittest

from platform_core.mobil import protocol

INSTALLATION = "9d8109a3-32fd-48e3-b921-252cb01ade71"
OPERATION = "12d67d64-a312-43d2-9afb-2eb7412561de"
RECORD = "5cc4515b-c67f-4ca9-8706-7768158f4df2"
SECRET = b"a" * 32


class ProtocolTest(unittest.TestCase):
	def test_ids_require_canonical_random_uuid(self):
		self.assertEqual(protocol.uuid4_id(INSTALLATION), INSTALLATION)
		for value in (INSTALLATION.upper(), "0" * 36, True, INSTALLATION.replace("-4", "-1")):
			with self.subTest(value=value), self.assertRaises(protocol.MobileError):
				protocol.uuid4_id(value)

	def test_operation_key_is_scoped_to_site_and_account(self):
		key = protocol.operation_key("one", "account", OPERATION)
		self.assertNotEqual(key, protocol.operation_key("two", "account", OPERATION))
		self.assertNotEqual(key, protocol.operation_key("one", "other", OPERATION))

	def test_digest_is_order_independent_but_covers_command_and_version(self):
		operation = {"command": "update", "record_id": RECORD, "version": "1", "fields": {"a": 2, "b": 1}}
		changed = dict(operation, fields={"b": 1, "a": 2})
		self.assertEqual(protocol.content_digest(operation), protocol.content_digest(changed))
		for field, value in (("command", "delete"), ("version", "2"), ("record_id", OPERATION)):
			self.assertNotEqual(
				protocol.content_digest(operation), protocol.content_digest(dict(operation, **{field: value}))
			)

	def test_version_conflict_exposes_only_projection_given_by_adapter(self):
		current = {"kind": "upsert", "record_type": "sample", "record_id": RECORD, "version": "2"}
		with self.assertRaises(protocol.MobileError) as error:
			protocol.check_version("1", current)
		self.assertEqual(error.exception.status, 409)
		self.assertEqual(error.exception.current, current)
		protocol.check_version("2", current)

	def test_cursor_keeps_position_and_boundaries(self):
		scope = ("site", "account", INSTALLATION)
		token = protocol.encode_cursor(SECRET, scope, after=42, ceiling=60, now=100)
		self.assertEqual(
			protocol.decode_cursor(SECRET, scope, token, now=101, floor=42), (42, 60, False, None, None)
		)
		for other_scope, other_token, now, floor in (
			(("other", *scope[1:]), token, 101, 0),
			((scope[0], "other", scope[2]), token, 101, 0),
			((*scope[:2], RECORD), token, 101, 0),
			(scope, token + "x", 101, 0),
			(scope, token, 100 + 7 * 86400, 0),
			(scope, token, 101, 43),
		):
			with self.subTest(scope=other_scope, now=now, floor=floor):
				with self.assertRaises(protocol.MobileError) as error:
					protocol.decode_cursor(SECRET, other_scope, other_token, now=now, floor=floor)
				self.assertEqual(error.exception.status, 410)

	def test_cursor_ciphertext_is_random_and_hides_sequence(self):
		scope = ("site", "account", INSTALLATION)
		args = {"after": 123456789, "ceiling": 987654321, "now": 100}
		first = protocol.encode_cursor(SECRET, scope, **args)
		second = protocol.encode_cursor(SECRET, scope, **args)
		self.assertNotEqual(first, second)
		body = first.split(".")[-1]
		raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
		self.assertNotIn(b"987654321", raw)

	def test_record_identifiers_are_scoped_to_principal_and_type(self):
		key = protocol.scoped_record_key("sample", "principal", RECORD)
		self.assertNotEqual(key, protocol.scoped_record_key("other", "principal", RECORD))
		self.assertNotEqual(key, protocol.scoped_record_key("sample", "other", RECORD))
		with self.assertRaises(protocol.MobileError):
			protocol.scoped_record_key("sample", "principal", "invalid")

	def test_allowlist_rejects_unregistered_command(self):
		operation = {"operation_id": OPERATION, "command": "anything", "record_id": RECORD}
		with self.assertRaises(protocol.MobileError) as error:
			protocol.validate_operation(operation, {})
		self.assertEqual(error.exception.code, "unknown_command")

	def test_command_requires_version_and_limits_fields(self):
		commands = {"sample.update": protocol.Command("update", frozenset({"title"}))}
		operation = {
			"operation_id": OPERATION,
			"command": "sample.update",
			"record_id": RECORD,
			"fields": {"title": "Sample"},
		}
		with self.assertRaises(protocol.MobileError):
			protocol.validate_operation(operation, commands)
		operation["version"] = "1"
		self.assertEqual(protocol.validate_operation(operation, commands), commands["sample.update"])
		operation["fields"]["owner"] = "Other"
		with self.assertRaises(protocol.MobileError):
			protocol.validate_operation(operation, commands)
