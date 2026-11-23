"""Exercise the collection summary through the tenant's HTTP and permission hooks."""

import json
from urllib.parse import urlencode

import frappe

from platform_core.tests.shell_http_fixture import PRIVILEGED, READER, ShellHTTPFixture

SUMMARY_DOCTYPE = "Shell Summary Test"
SUMMARY_PATH = "/api/method/platform_core.api.collection.group_summary"


class TestCollectionSummary(ShellHTTPFixture):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("DocType", SUMMARY_DOCTYPE):
			frappe.get_doc(
				doctype="DocType",
				name=SUMMARY_DOCTYPE,
				module="Shell",
				custom=1,
				fields=[
					{"fieldname": "bucket", "fieldtype": "Data", "label": "Bucket"},
					{"fieldname": "amount", "fieldtype": "Currency", "label": "Amount"},
					{
						"fieldname": "private_amount",
						"fieldtype": "Currency",
						"label": "Private amount",
						"permlevel": 1,
					},
					{
						"fieldname": "assigned_user",
						"fieldtype": "Link",
						"label": "Assigned user",
						"options": "User",
					},
				],
				permissions=[
					{"role": "Kabuk Test Reader", "read": 1},
					{"role": "Kabuk Test Privileged", "read": 1},
					{"role": "Kabuk Test Privileged", "read": 1, "permlevel": 1},
				],
			).insert()
		rule = frappe.get_doc(
			doctype="PLT Access Rule",
			title="Summary reader scope",
			document_type=SUMMARY_DOCTYPE,
			role="Kabuk Test Reader",
			is_active=1,
			scope="own",
			match_field="assigned_user",
			allow_read=1,
		).insert()
		cls.addClassCleanup(cls.remove_fixture, rule.doctype, rule.name)
		fixture_rows = [("A", 8, READER), ("A", 12, READER), ("A", 900, PRIVILEGED)]
		fixture_rows.extend([("B", 3, READER)] * 22)
		for bucket, amount, owner in fixture_rows:
			record = frappe.get_doc(
				doctype=SUMMARY_DOCTYPE,
				bucket=bucket,
				amount=amount,
				private_amount=amount,
				assigned_user=owner,
				owner=owner,
			).insert()
			cls.addClassCleanup(cls.remove_fixture, record.doctype, record.name)
		frappe.db.commit()

	@staticmethod
	def remove_fixture(doctype, name):
		frappe.delete_doc(doctype, name, force=True)
		frappe.db.commit()

	def summary_request(self, sid, **overrides):
		params = {"doctype": SUMMARY_DOCTYPE, "group_by": "bucket", **overrides}
		status, _unused_headers, body = self.request(f"{SUMMARY_PATH}?{urlencode(params)}", sid)
		return status, json.loads(body)

	def test_group_summary_foreign_data_denied(self):
		status, response = self.summary_request(
			self.reader_sid, aggregate="sum", aggregate_field="amount", limit=1
		)
		self.assertEqual(status, 200)
		self.assertEqual(
			response["message"],
			{
				"groups": [{"value": "A", "count": 2, "aggregate": 20}],
				"total_count": 24,
				"truncated": True,
			},
		)

		status, response = self.summary_request(
			self.privileged_sid, aggregate="sum", aggregate_field="amount"
		)
		self.assertEqual(status, 200)
		self.assertEqual(response["message"]["groups"], [{"value": "A", "count": 1, "aggregate": 900}])

	def test_collection_rate_limit_is_per_account(self):
		key = frappe.cache.make_key(f"rl:platform_core.api.collection.group_summary:{READER}") + b":60"
		frappe.cache.setex(key, 60, 119)
		try:
			self.assertEqual(self.summary_request(self.reader_sid)[0], 200)
			status, response = self.summary_request(self.reader_sid)
			self.assertEqual(status, 429)
			self.assertEqual(response["exc_type"], "RateLimitExceededError")
			self.assertEqual(self.summary_request(self.privileged_sid)[0], 200)
		finally:
			frappe.cache.delete(key)

	def test_average_and_filter_apply_to_visible_rows(self):
		status, response = self.summary_request(
			self.reader_sid,
			aggregate="avg",
			aggregate_field="amount",
			filters=json.dumps([["bucket", "=", "A"]]),
		)
		self.assertEqual(status, 200)
		self.assertEqual(
			response["message"],
			{
				"groups": [{"value": "A", "count": 2, "aggregate": 10}],
				"total_count": 2,
				"truncated": False,
			},
		)

	def test_invalid_parameters_and_unreadable_fields_are_rejected(self):
		for expected, overrides in (
			(400, {"group_by": "missing_field"}),
			(400, {"group_by": "bucket, amount"}),
			(400, {"limit": 101}),
			(400, {"filters": json.dumps([[None, "=", 1]])}),
			(400, {"filters": json.dumps([["User", "name", "=", READER]])}),
			(400, {"aggregate": "sum", "aggregate_field": "bucket"}),
			(400, {"aggregate": "avg"}),
			(403, {"group_by": "private_amount"}),
			(403, {"aggregate": "sum", "aggregate_field": "private_amount"}),
			(403, {"filters": json.dumps({"private_amount": 900})}),
			(403, {"doctype": "PLT Access Rule", "group_by": "name"}),
			(404, {"doctype": "Missing Summary Type"}),
		):
			with self.subTest(overrides=overrides):
				status, _unused_response = self.summary_request(self.reader_sid, **overrides)
				self.assertEqual(status, expected)

	def test_group_summary_guest_denied(self):
		status, _unused_response = self.summary_request(None)
		self.assertEqual(status, 403)
