"""Opt-in HTTP checks against an isolated Frappe test site."""

import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from time import monotonic, sleep, time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

FIXTURE = os.environ.get("MOBILE_TEST_FIXTURE") == "1"
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
		return self.post_method(
			f"platform_core.api.mobile.{endpoint}", data, token, suffix=suffix, extra_headers=extra_headers
		)

	def post_method(self, method, data, token, *, suffix="", extra_headers=None):
		headers = {
			"Content-Type": "application/json",
			"X-Mobile-App-Version": "1.0.0",
			"X-Mobile-Contract-Version": "1",
		}
		if token:
			headers["Authorization"] = f"Bearer {token}"
		headers.update(extra_headers or {})
		request = Request(
			f"{BASE}/api/method/{method}{suffix}",
			data=data if isinstance(data, bytes) else json.dumps(data).encode(),
			headers=headers,
			method="POST",
		)
		try:
			with urlopen(request, timeout=15) as response:
				return response.status, json.load(response), response.headers
		except HTTPError as error:
			with error:
				return error.code, json.load(error), error.headers

	def register(self, *, token=TOKEN, extra_headers=None):
		body = {"installation_id": str(uuid4())}
		status, payload, _ = self.post("v1_register", body, token=token, extra_headers=extra_headers)
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
		token = "fixture-revoke-one" if FIXTURE else TOKEN
		body = self.register(token=token)
		self.assertEqual(self.post("v1_revoke", body, token=token)[0], 200)
		for endpoint in ("v1_pull", "v1_register"):
			status, result, _ = self.post(endpoint, body, token=token)
			self.assertEqual((status, result.get("code")), (401, "mobile_session_revoked"), result)
		if FIXTURE:
			status, payload, _ = self.post(
				"v1_register",
				{"installation_id": str(uuid4())},
				token=token,
				extra_headers={"X-Mobile-Test-Iat": str(int(time()) - 60), "X-Mobile-Test-Sid": str(uuid4())},
			)
			self.assertEqual(status, 403, payload)

	@unittest.skipUnless(FIXTURE, "Synthetic token issuance timestamps are required")
	def test_revoke_all_rejects_stale_token_for_new_installation(self):
		old = {"X-Mobile-Test-Iat": str(int(time()))}
		self.register(token="fixture-revoke", extra_headers=old)
		status, payload, _ = self.post("v1_revoke", {"all": True}, token="fixture-revoke", extra_headers=old)
		self.assertEqual(status, 200, payload)
		fresh_installation = {"installation_id": str(uuid4())}
		status, payload, _ = self.post(
			"v1_register",
			fresh_installation,
			token="fixture-revoke",
			extra_headers=old,
		)
		self.assertEqual((status, payload.get("code")), (401, "mobile_session_revoked"), payload)
		# Send a new issuance and session after the cutoff, within the allowed clock skew.
		issued_after = int(time()) + 31
		while int(time()) + 30 < issued_after:
			sleep(0.02)
		fresh = {"X-Mobile-Test-Iat": str(issued_after), "X-Mobile-Test-Sid": str(uuid4())}
		status, payload, _ = self.post(
			"v1_register",
			fresh_installation,
			token="fixture-revoke",
			extra_headers=fresh,
		)
		self.assertEqual(status, 200, payload)

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

	@unittest.skipUnless(FIXTURE, "The fixture lets an empty cmd reach the mobile endpoint")
	def test_mobile_identity_rejects_cmd_query_even_with_json_body(self):
		status, payload, _ = self.post("v1_register", {"installation_id": str(uuid4())}, suffix="?cmd=")
		self.assertEqual((status, payload.get("code")), (400, "invalid_mobile_route"), payload)

	@unittest.skipUnless(FIXTURE, "Synthetic identity marker is required")
	def test_request_gate_rejects_untrusted_identity_and_invalid_body(self):
		for marker in ("site", "scope", "account"):
			with self.subTest(marker=marker):
				status, payload, _ = self.post(
					"v1_register",
					{"installation_id": str(uuid4())},
					extra_headers={"X-Mobile-Test-Identity-Mismatch": marker},
				)
				self.assertEqual((status, payload.get("code")), (401, "mobile_token_required"))
		for content, headers, status_expected, code in (
			(b'{"cmd":""}', {}, 400, "invalid_mobile_route"),
			(b'{"installation_id":"one","installation_id":"two"}', {}, 400, "invalid_json"),
			(b"not JSON", {"Content-Type": "text/plain"}, 415, "json_required"),
		):
			with self.subTest(code=code):
				status, payload, _ = self.post("v1_register", content, extra_headers=headers)
				self.assertEqual((status, payload.get("code")), (status_expected, code))

	def pull_all(self, body, cursor=None, *, token=TOKEN):
		changes = []
		while True:
			request = dict(body, cursor=cursor) if cursor is not None else body
			status, payload, _ = self.post("v1_pull", request, token=token)
			self.assertEqual(status, 200, payload)
			message = payload["message"]
			changes.extend(message["changes"])
			next_cursor = message["cursor"]
			if not message.get("has_more"):
				return changes, next_cursor
			self.assertNotEqual(cursor, next_cursor, "A continuation must advance")
			cursor = next_cursor

	def commit_probe(self, record_id, release=False):
		status, payload, _ = self.post_method(
			"mobile_test_app.fixture.commit_probe",
			{"record_id": record_id, "release": release},
			"fixture-control",
		)
		self.assertEqual(status, 200, payload)
		return payload["message"]

	def wait_for_writer(self, record_id, state):
		deadline = monotonic() + 3
		while monotonic() < deadline:
			if self.commit_probe(record_id)[state]:
				return
			sleep(0.03)
		self.fail(f"Parallel worker did not observe {state}")

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

		initial_changes, cursor = self.pull_all(body)
		versions = {
			change["record_id"]: change["version"]
			for change in initial_changes
			if change["record_id"] in ids and change["kind"] == "upsert"
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

		changes, _ = self.pull_all(body, cursor)
		changes = [change for change in changes if change["record_id"] in ids]
		self.assertEqual({change["record_id"] for change in changes}, set(ids))
		for change in changes:
			self.assertEqual(change.keys(), {"record_id", "record_type", "kind"})
			self.assertEqual(change["kind"], "remove")
		replayed, _ = self.pull_all(body, cursor)
		self.assertEqual([change for change in replayed if change["record_id"] in ids], changes)

	@unittest.skipUnless(
		os.environ.get("MOBILE_TEST_FIXTURE") == "1", "Synthetic business commands are required"
	)
	def test_concurrent_writes_are_both_delivered(self):
		body = self.register()
		fast_body = self.register(token=OTHER_TOKEN)
		_, cursor = self.pull_all(body)
		_, fast_cursor = self.pull_all(fast_body, token=OTHER_TOKEN)
		# Complete initial audits before probing a read-only delta page during the held write.
		_, cursor = self.pull_all(body, cursor)
		_, fast_cursor = self.pull_all(fast_body, fast_cursor, token=OTHER_TOKEN)
		delayed_id, fast_id = str(uuid4()), str(uuid4())
		delayed_request = self.fixture_operation(
			body, "create", delayed_id, fields={"title": "Delayed fixture"}
		)
		fast_request = self.fixture_operation(
			fast_body, "create", fast_id, fields={"title": "Concurrent fixture"}
		)

		with ThreadPoolExecutor() as executor:
			delayed = executor.submit(self.post, "v1_push", delayed_request)
			try:
				# This signal is published from before_commit after the sequence was assigned.
				self.wait_for_writer(delayed_id, "pending")
				self.assertFalse(delayed.done(), "The first transaction must still be open")
				fast = executor.submit(
					self.post,
					"v1_push",
					fast_request,
					OTHER_TOKEN,
					extra_headers={"X-Mobile-Test-Writer": delayed_id},
				)
				self.wait_for_writer(delayed_id, "entered")
				# Give a writer without a sequence lock a chance to commit out of order.
				try:
					fast.result(timeout=0.5)
				except TimeoutError:
					pass
				between, cursor = self.pull_all(body, cursor)
				self.assertFalse(delayed.done(), "The delta must return while the first commit is held")
				self.assertNotIn(delayed_id, {change["record_id"] for change in between})
			finally:
				self.commit_probe(delayed_id, release=True)
			for future in (delayed, fast):
				status, result, _ = future.result()
				self.assertEqual(status, 200, result)

		last, _ = self.pull_all(body, cursor)
		fast_changes, _ = self.pull_all(fast_body, fast_cursor, token=OTHER_TOKEN)
		self.assertIn(delayed_id, {change["record_id"] for change in last})
		self.assertIn(fast_id, {change["record_id"] for change in fast_changes})

	@unittest.skipUnless(FIXTURE, "Synthetic business commands are required")
	def test_foreign_uuid_is_indistinguishable_from_missing_record(self):
		body = self.register()
		record_id = str(uuid4())
		operation = self.fixture_operation(body, "create", record_id, fields={"title": "Example"})
		self.assertEqual(self.post("v1_push", operation)[0], 200)
		foreign = self.register(token=OTHER_TOKEN)
		attempts = (
			self.fixture_operation(foreign, "create", record_id, fields={"title": "Other"}),
			self.fixture_operation(foreign, "update", record_id, version="old"),
			self.fixture_operation(foreign, "update", str(uuid4()), version="old"),
		)
		for attempt in attempts:
			status, payload, _ = self.post("v1_push", attempt, token=OTHER_TOKEN)
			self.assertEqual((status, payload.get("code")), (404, "record_not_found"), payload)

	@unittest.skipUnless(FIXTURE, "Synthetic business commands are required")
	def test_mismatched_scope_key_excludes_owned_record(self):
		body = self.register()
		record_id = str(uuid4())
		operation = self.fixture_operation(
			body, "create_bad_scope", record_id, fields={"title": "Wrong scope"}
		)
		status, payload, _ = self.post("v1_push", operation)
		self.assertEqual(status, 200, payload)

		changes, _ = self.pull_all(body)
		self.assertNotIn(record_id, {change["record_id"] for change in changes})
		attempt = self.fixture_operation(body, "update", record_id, version="old")
		status, payload, _ = self.post("v1_push", attempt)
		self.assertEqual((status, payload.get("code")), (404, "record_not_found"), payload)

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

	@unittest.skipUnless(FIXTURE, "Synthetic service markers are required")
	def test_revoke_user_installations_guest_denied(self):
		status, _, _ = self.post("revoke_user_installations", {}, token=None)
		self.assertIn(status, {401, 403})

	@unittest.skipUnless(FIXTURE, "Synthetic service markers are required")
	def test_revoke_user_installations_foreign_data_denied(self):
		status, _, _ = self.post(
			"revoke_user_installations",
			{"issuer": "fixture", "subject": "missing"},
			token="fixture-service-other",
		)
		self.assertEqual(status, 403)
