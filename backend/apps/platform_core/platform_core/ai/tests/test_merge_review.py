"""Rules decided after the pre-merge review.

Blocker: the field property tool checks the current property under a lock that also covers the
first insert. If another transaction changed or added the property after the human saw the
preview, nothing is written and a new proposal is needed.
Major: the byte limit of a DocType definition covers the whole result, description included.
Minor: the translation file uses LF line endings.
"""

import json
from pathlib import Path
from unittest.mock import patch

import frappe

import platform_core
from platform_core.ai.tests.base import DOCTYPE, MANAGER, USER_A, AiTestCase

FIELD = "title"
PROPERTY = "description"
KEY = {"doc_type": DOCTYPE, "field_name": FIELD, "property": PROPERTY}


def remove_setters() -> None:
	for name in frappe.get_all("Property Setter", filters=KEY, pluck="name"):
		frappe.delete_doc("Property Setter", name, force=True)
	frappe.clear_cache(doctype=DOCTYPE)


def add_setter(value: str) -> None:
	frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocField",
			"property_type": "Text",
			"value": value,
			**KEY,
		}
	).insert()
	frappe.clear_cache(doctype=DOCTYPE)


class TestFieldPropertyUnderLock(AiTestCase):
	def setUp(self):
		super().setUp()
		self.reset()
		self.addCleanup(self.reset)

	def reset(self):
		frappe.set_user("Administrator")
		remove_setters()
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

	def propose(self, client, value: str) -> str:
		arguments = {"doctype": DOCTYPE, "fieldname": FIELD, "property": PROPERTY, "value": value}
		result = self.call_tool(client, "plt_set_field_property", arguments)
		self.assertFalse(result["isError"], result)
		return result["structuredContent"]["proposal_id"]

	def approve_while(self, client, proposal_id: str, rival) -> dict:
		"""Approve while `rival` commits on another connection after this request's first plain read.

		The plain read pins the snapshot of a repeatable read transaction, so every later plain
		read of the request still sees the data from before the rival's commit.
		"""
		from platform_core.ai import proposals

		digest = self.digest_of(client, proposal_id)
		original = proposals._pre_check

		def pinned_snapshot_then_rival(*args, **kwargs):
			frappe.get_all("Property Setter", filters=KEY, pluck="name")
			self.in_other_connection(rival)
			return original(*args, **kwargs)

		# The proposal is R3. The rival runs at the second approval, where the action executes.
		around = patch.object(proposals, "_pre_check", pinned_snapshot_then_rival)
		return self.approve_both(client, proposal_id, digest, around_second=around).json["message"]

	def setter_values(self) -> list[str]:
		frappe.db.rollback()
		return frappe.get_all("Property Setter", filters=KEY, pluck="value")

	def assert_stopped(self, outcome: dict) -> None:
		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(
			(outcome["proposal"]["result"], outcome["proposal"]["error"]), ("failed", "document_changed")
		)

	def test_existing_property_changed_by_another_transaction_stops_the_write(self):
		add_setter("First")
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		manager = self.login(MANAGER)
		proposal_id = self.propose(manager, "From AI")

		def rival():
			name = frappe.get_all("Property Setter", filters=KEY, pluck="name")[0]
			frappe.db.set_value("Property Setter", name, "value", "From rival")

		outcome = self.approve_while(manager, proposal_id, rival)

		self.assert_stopped(outcome)
		self.assertEqual(self.setter_values(), ["From rival"])

	def test_first_property_added_by_another_transaction_stops_the_write(self):
		manager = self.login(MANAGER)
		proposal_id = self.propose(manager, "From AI")

		outcome = self.approve_while(manager, proposal_id, lambda: add_setter("From rival"))

		self.assert_stopped(outcome)
		self.assertEqual(self.setter_values(), ["From rival"])

	def test_field_definition_changed_by_another_transaction_stops_the_write(self):
		"""The lock also covers the field's own definition row, not only its "Property Setter" rows."""
		field_row = {"parent": DOCTYPE, "fieldname": FIELD}
		original = frappe.db.get_value("DocField", field_row, PROPERTY)

		def restore():
			frappe.db.set_value("DocField", field_row, PROPERTY, original)
			frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
			frappe.clear_cache(doctype=DOCTYPE)

		self.addCleanup(restore)
		manager = self.login(MANAGER)
		proposal_id = self.propose(manager, "From AI")

		outcome = self.approve_while(
			manager, proposal_id, lambda: frappe.db.set_value("DocField", field_row, PROPERTY, "From rival")
		)

		self.assert_stopped(outcome)
		self.assertEqual(self.setter_values(), [])

	def test_unchanged_property_is_written(self):
		manager = self.login(MANAGER)

		first = self.approve_both(manager, self.propose(manager, "From AI")).json["message"]
		second = self.approve_both(manager, self.propose(manager, "Again")).json["message"]

		self.assertTrue(first["executed"], first)
		self.assertTrue(second["executed"], second)
		self.assertEqual(self.setter_values(), ["Again"])

	def test_current_property_is_read_with_a_locking_read_before_any_plain_read(self):
		from platform_core.ai.tools import admin

		frappe.set_user(MANAGER)
		reads = []
		original = frappe.db.get_values

		def spy(doctype, *args, **kwargs):
			reads.append((doctype, bool(kwargs.get("for_update"))))
			return original(doctype, *args, **kwargs)

		frappe.db.rollback()
		with patch.object(frappe.db, "get_values", spy):
			admin.prepare_field_property(DOCTYPE, FIELD, PROPERTY, "From AI")

		self.assertEqual(reads[0], ("Property Setter", True), reads[:3])


class TestWholeDefinitionFitsTheLimit(AiTestCase):
	def test_description_counts_toward_the_byte_limit(self):
		from platform_core.ai.tools import definition

		original = frappe.db.get_value("DocType", DOCTYPE, "description")

		def restore():
			frappe.db.set_value("DocType", DOCTYPE, "description", original)
			frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
			frappe.clear_cache(doctype=DOCTYPE)

		self.addCleanup(restore)
		frappe.db.set_value("DocType", DOCTYPE, "description", "d" * 5000)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		frappe.clear_cache(doctype=DOCTYPE)
		client = self.login(USER_A)

		with patch.object(definition, "MAX_RESULT_BYTES", 1500):
			body = self.call_tool(client, "plt_get_doctype_schema", {"doctype": DOCTYPE})["structuredContent"]

		data = {key: value for key, value in body.items() if key not in ("as_of", "site", "source")}
		self.assertLessEqual(len(json.dumps(data)), 1500)
		self.assertTrue(body["truncated"])
		self.assertTrue(body["description"].startswith("d"))
		self.assertLess(len(body["description"]), 5000)

	def test_definition_under_the_limit_is_whole(self):
		client = self.login(USER_A)

		body = self.call_tool(client, "plt_get_doctype_schema", {"doctype": DOCTYPE})["structuredContent"]

		self.assertFalse(body["truncated"])
		self.assertEqual(body["description"], frappe.get_meta(DOCTYPE).description)


class TestTranslationFileFormat(AiTestCase):
	def test_translation_file_uses_lf_line_endings(self):
		raw = (Path(platform_core.__file__).parent / "translations" / "tr.csv").read_bytes()

		self.assertNotIn(b"\r", raw)
		self.assertTrue(raw.endswith(b"\n"))
