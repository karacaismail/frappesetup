"""Opt-in HTTP checks against an isolated Frappe test site."""

import json
import os
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = os.environ.get("MOBILE_TEST_URL")
TOKEN = os.environ.get("MOBILE_TEST_BEARER")
OTHER_TOKEN = os.environ.get("MOBILE_TEST_OTHER_BEARER")


@unittest.skipUnless(
	BASE and TOKEN and OTHER_TOKEN, "An isolated Frappe site and two test tokens are required"
)
class MobileHTTPTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		host = urlsplit(BASE).hostname
		if host not in {"localhost", "127.0.0.1", "::1"}:
			raise ValueError("HTTP tests are restricted to loopback")

	def post(self, endpoint, data, token=TOKEN, *, suffix="", extra_headers=None):
		headers = {
			"Content-Type": "application/json",
			"X-Mobile-App-Version": "1.0.0",
			"X-Mobile-Contract-Version": "1",
		}
		if token:
			headers["Authorization"] = f"Bearer {token}"
		headers.update(extra_headers or {})
		request = Request(
			f"{BASE}/api/method/platform_core.api.mobile.{endpoint}{suffix}",
			data=json.dumps(data).encode(),
			headers=headers,
			method="POST",
		)
		try:
			with urlopen(request, timeout=15) as response:
				return response.status, json.load(response), response.headers
		except HTTPError as error:
			with error:
				return error.code, json.load(error), error.headers

	def register(self):
		body = {"installation_id": str(uuid4())}
		status, payload, _ = self.post("v1_register", body)
		self.assertEqual(status, 200, payload)
		self.assertEqual(payload["message"], body)
		return body

	def guest_denied(self, endpoint, body):
		status, payload, _ = self.post(endpoint, body, token=None)
		self.assertIn(status, {401, 403}, payload)

	def test_v1_register_guest_denied(self):
		self.guest_denied("v1_register", {"installation_id": str(uuid4())})

	def test_v1_register_foreign_data_denied(self):
		status, payload, _ = self.post("v1_register", self.register(), token=OTHER_TOKEN)
		self.assertEqual(status, 403, payload)

	def test_v1_revoke_guest_denied(self):
		self.guest_denied("v1_revoke", {"all": True})

	def test_v1_revoke_foreign_data_denied(self):
		body = self.register()
		status, payload, _ = self.post("v1_revoke", body, token=OTHER_TOKEN)
		self.assertEqual(status, 200, payload)
		self.assertEqual(payload["message"], {"revoked": 0})
		self.assertEqual(self.post("v1_pull", body)[0], 200)

	def test_v1_push_guest_denied(self):
		self.guest_denied("v1_push", {"installation_id": str(uuid4()), "operations": []})

	def test_v1_push_foreign_data_denied(self):
		body = dict(self.register(), operations=[])
		status, payload, _ = self.post("v1_push", body, token=OTHER_TOKEN)
		self.assertEqual(status, 403, payload)

	def test_v1_pull_guest_denied(self):
		self.guest_denied("v1_pull", {"installation_id": str(uuid4())})

	def test_v1_pull_foreign_data_denied(self):
		status, payload, _ = self.post("v1_pull", self.register(), token=OTHER_TOKEN)
		self.assertEqual(status, 403, payload)

	def test_v1_cleanup_guest_denied(self):
		self.guest_denied("v1_cleanup", {})

	def test_v1_cleanup_foreign_data_denied(self):
		status, payload, _ = self.post("v1_cleanup", {}, token=OTHER_TOKEN)
		self.assertEqual(status, 403, payload)

	def test_revoke_prevents_reads_and_reactivation(self):
		body = self.register()
		self.assertEqual(self.post("v1_revoke", body)[0], 200)
		self.assertEqual(self.post("v1_pull", body)[0], 403)
		self.assertEqual(self.post("v1_register", body)[0], 403)

	def test_body_above_contract_limit_returns_413(self):
		status, payload, _ = self.post("v1_register", {"extra": "a" * (256 * 1024)})
		self.assertEqual(status, 413, payload)

	def test_v1_remains_available_for_the_original_client_version(self):
		body = self.register()
		status, response, _ = self.post("v1_pull", body)
		self.assertEqual(status, 200, response)
		continuation = dict(body, cursor=response["message"]["cursor"])
		status, response, _ = self.post(
			"v1_pull",
			continuation,
			extra_headers={"X-Mobile-Contract-Version": "2"},
		)
		self.assertEqual((status, response.get("code")), (400, "unsupported_contract_version"))
		status, response, _ = self.post("v1_pull", continuation)
		self.assertEqual(status, 200, response)
		self.assertIn("changes", response["message"])

	def test_mobile_identity_rejects_cmd_query_even_with_json_body(self):
		status, payload, _ = self.post("v1_register", {"installation_id": str(uuid4())}, suffix="?cmd=")
		self.assertIn(status, {400, 401, 403}, payload)

	def fixture_operation(self, body, action, record_id, **values):
		operation = {
			"operation_id": str(uuid4()),
			"command": f"fixture.{action}",
			"record_id": record_id,
			**values,
		}
		return dict(body, operations=[operation])

	@unittest.skipUnless(
		os.environ.get("MOBILE_TEST_FIXTURE") == "1", "Synthetic business commands are required"
	)
	def test_retry_conflict_version_delete_and_permission_loss(self):
		body = self.register()
		ids = [str(uuid4()), str(uuid4())]
		for record_id in ids:
			operation = self.fixture_operation(body, "create", record_id, fields={"title": "Example"})
			status, result, _ = self.post("v1_push", operation)
			self.assertEqual(status, 200, result)
			self.assertEqual(self.post("v1_push", operation)[:2], (status, result))
			operation["operations"][0]["fields"]["title"] = "Different"
			status, result, _ = self.post("v1_push", operation)
			self.assertEqual((status, result.get("code")), (409, "operation_conflict"), result)

		status, first, _ = self.post("v1_pull", body)
		self.assertEqual(status, 200, first)
		versions = {
			change["record_id"]: change["version"]
			for change in first["message"]["changes"]
			if change["record_id"] in ids
		}
		stale = self.fixture_operation(body, "update", ids[0], version="old", fields={"title": "Updated"})
		status, result, _ = self.post("v1_push", stale)
		self.assertEqual((status, result.get("code")), (409, "version_conflict"), result)
		self.assertEqual(result["current"]["version"], versions[ids[0]])

		for action, record_id in zip(("delete", "transfer"), ids, strict=True):
			status, result, _ = self.post(
				"v1_push",
				self.fixture_operation(body, action, record_id, version=versions[record_id]),
			)
			self.assertEqual(status, 200, result)

		continuation = dict(body, cursor=first["message"]["cursor"])
		status, response, _ = self.post("v1_pull", continuation)
		self.assertEqual(status, 200, response)
		changes = [change for change in response["message"]["changes"] if change["record_id"] in ids]
		self.assertEqual({change["record_id"] for change in changes}, set(ids))
		for change in changes:
			self.assertEqual(change.keys(), {"record_id", "record_type", "kind"})
			self.assertEqual(change["kind"], "remove")
		retry_status, retry_response, _ = self.post("v1_pull", continuation)
		self.assertEqual(retry_status, 200, retry_response)
		self.assertEqual(retry_response["message"]["changes"], response["message"]["changes"])

	@unittest.skipUnless(
		os.environ.get("MOBILE_TEST_FIXTURE") == "1", "Synthetic business commands are required"
	)
	def test_concurrent_writes_are_both_delivered(self):
		from concurrent.futures import ThreadPoolExecutor
		from time import sleep

		body = self.register()
		status, first, _ = self.post("v1_pull", body)
		self.assertEqual(status, 200, first)
		ids = [str(uuid4()), str(uuid4())]
		requests = [
			self.fixture_operation(body, "create", ids[0], fields={"title": "Delayed fixture"}),
			self.fixture_operation(body, "create", ids[1], fields={"title": "Concurrent fixture"}),
		]

		with ThreadPoolExecutor() as executor:
			delayed = executor.submit(self.post, "v1_push", requests[0])
			sleep(0.1)
			fast = executor.submit(self.post, "v1_push", requests[1])
			between = self.post("v1_pull", dict(body, cursor=first["message"]["cursor"]))
			for future in (delayed, fast):
				status, result, _ = future.result()
				self.assertEqual(status, 200, result)

		self.assertEqual(between[0], 200, between[1])
		status, last, _ = self.post("v1_pull", dict(body, cursor=between[1]["message"]["cursor"]))
		self.assertEqual(status, 200, last)
		seen = {
			change["record_id"] for payload in (between[1], last) for change in payload["message"]["changes"]
		}
		self.assertTrue(set(ids) <= seen, seen)

	@unittest.skipUnless(
		os.environ.get("MOBILE_TEST_FIXTURE") == "1", "Synthetic business commands are required"
	)
	def test_batch_rolls_back_earlier_effects_on_failure(self):
		body = self.register()
		record_id = str(uuid4())
		valid = self.fixture_operation(body, "create", record_id, fields={"title": "Example"})
		invalid = self.fixture_operation(body, "unsupported", str(uuid4()))
		batch = dict(body, operations=valid["operations"] + invalid["operations"])
		status, result, _ = self.post("v1_push", batch)
		self.assertEqual((status, result.get("code")), (400, "unknown_command"), result)
		self.assertEqual(self.post("v1_push", valid)[0], 200)

	@unittest.skipUnless(
		os.environ.get("MOBILE_TEST_FIXTURE") == "1", "Synthetic rate-test account is required"
	)
	def test_rate_limit_returns_429_with_retry_after(self):
		body = {"installation_id": str(uuid4())}
		for _ in range(121):
			status, result, headers = self.post("v1_register", body, token="fixture-rate")
			if status == 429:
				self.assertEqual(result.get("code"), "rate_limit")
				self.assertTrue(1 <= int(headers["Retry-After"]) <= 60)
				return
			self.assertEqual(status, 200, result)
		self.fail("Rate limit was not applied")
