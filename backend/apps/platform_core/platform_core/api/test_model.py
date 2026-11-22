"""Real HTTP checks run by the disposable model gateway fixture."""

import json
import unittest
from time import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

import frappe
from frappe.utils import add_days, now_datetime
from frappe.utils.password import get_decrypted_password

from platform_core.model_gecidi import adapters, gateway, policy


class TestModelHTTP(unittest.TestCase):
	fixture = None

	@classmethod
	def setUpClass(cls):
		if cls.fixture is None:
			raise unittest.SkipTest("Run the disposable Frappe HTTP fixture")

	def setUp(self):
		self.fixture["provider_payloads"].clear()
		for api in (self.fixture["first_api"], self.fixture["second_api"]):
			frappe.cache.delete(self._cooldown_key(api))
			frappe.db.delete("AI Usage Log", {"api": api})
		frappe.db.commit()
		self.fixture["provider_status"]["/first/api/chat"] = 429

	def _cooldown_key(self, api):
		return frappe.cache.make_key(f"model_gateway:cooldown:{api}")

	def request(self, actor, method, path, **kwargs):
		session = self.fixture["sessions"][actor]
		if actor in {"agent", "api_key"}:
			session.cookies.clear()
		return session.request(
			method, self.fixture["base"] + path, timeout=15, allow_redirects=False, **kwargs
		)

	def resource(self, doctype, name=""):
		path = "/api/resource/" + quote(doctype, safe="")
		if name:
			path += "/" + quote(name, safe="")
		return path

	def complete(self, actor, route=None):
		return self.request(
			actor,
			"POST",
			"/api/method/platform_core.api.model.complete",
			json={
				"route": route or self.fixture["route"],
				"messages": [{"role": "user", "content": "fixture message for failover"}],
				"limit": 12,
			},
		)

	def _test_api_request(self, actor):
		return self.request(
			actor,
			"POST",
			"/api/method/platform_core.api.model.test_api",
			json={"api": self.fixture["second_api"], "model": self.fixture["model"]},
		)

	def test_complete_guest_denied(self):
		self.assertIn(self.complete("guest").status_code, {401, 403})

	def test_complete_foreign_data_denied(self):
		self.assertEqual(self.complete("regular").status_code, 403)

	def test_test_api_guest_denied(self):
		self.assertIn(self._test_api_request("guest").status_code, {401, 403})

	def test_test_api_foreign_data_denied(self):
		self.assertEqual(self._test_api_request("regular").status_code, 403)

	def test_regular_user_cannot_list_or_read_provider_credentials(self):
		for name in ("", self.fixture["credential_api"]):
			with self.subTest(detail=bool(name)):
				response = self.request("regular", "GET", self.resource("AI API", name))
				self.assertEqual(response.status_code, 403)

	def test_manager_can_read_api_without_getting_secret(self):
		name = self.fixture["credential_api"]
		detail = self.request("manager", "GET", self.resource("AI API", name))
		self.assertEqual(detail.status_code, 200)
		self.assertEqual(detail.json()["data"]["name"], name)
		self.assertNotIn("api_key", detail.json()["data"])
		listing = self.request(
			"manager",
			"GET",
			self.resource("AI API"),
			params={"fields": json.dumps(["name", "api_key"]), "filters": json.dumps({"name": name})},
		)
		self.assertIn(listing.status_code, {200, 403, 417})
		if listing.ok:
			self.assertNotIn("api_key", listing.json()["data"][0])
		document = self.request(
			"manager",
			"GET",
			"/api/method/frappe.client.get",
			params={"doctype": "AI API", "name": name},
		)
		self.assertEqual(document.status_code, 200)
		self.assertEqual(document.json()["message"]["name"], name)
		self.assertNotIn("api_key", document.json()["message"])
		for response in (detail, listing, document):
			self.assertTrue(self.fixture["credential"] not in response.text)

	def test_manager_can_test_one_api(self):
		count = len(self.fixture["attempts"])
		response = self._test_api_request("manager")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["message"]["api"], self.fixture["second_api"])
		self.assertEqual(self.fixture["attempts"][count:], ["/second/api/chat"])

	def test_route_falls_back_to_another_account_and_api(self):
		count = len(self.fixture["attempts"])
		route = self.fixture["route"]
		response = self.complete("manager")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["message"]["api"], self.fixture["second_api"])
		self.assertEqual(self.fixture["attempts"][count:], ["/first/api/chat", "/second/api/chat"])
		usage = self.request(
			"manager",
			"GET",
			self.resource("AI Usage Log"),
			params={"filters": json.dumps({"route": route}), "fields": '["*"]'},
		)
		self.assertEqual(usage.status_code, 200)
		records = usage.json()["data"]
		self.assertEqual(len(records), 2)
		self.assertNotIn("fixture message for failover", usage.text)
		attempts = {(item["api"], item["account"]) for item in records}
		expected = {
			(self.fixture["first_api"], self.fixture["first_account"]),
			(self.fixture["second_api"], self.fixture["second_account"]),
		}
		self.assertEqual(attempts, expected)

	def test_route_rejects_agent_token(self):
		count = len(self.fixture["attempts"])
		self.assertIn(self.complete("agent").status_code, {401, 403})
		self.assertIn(self._test_api_request("agent").status_code, {401, 403})
		self.assertEqual(len(self.fixture["attempts"]), count)

	def test_ordinary_user_with_matching_role_can_complete(self):
		count = len(self.fixture["attempts"])
		response = self.complete("authorized", self.fixture["role_route"])
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(response.json()["message"]["api"], self.fixture["second_api"])
		self.assertEqual(self.fixture["attempts"][count:], ["/second/api/chat"])

	def test_native_api_key_authenticates_model_completion(self):
		count = len(self.fixture["attempts"])
		response = self.complete("api_key", self.fixture["role_route"])
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(response.json()["message"]["api"], self.fixture["second_api"])
		self.assertEqual(self.fixture["attempts"][count:], ["/second/api/chat"])

	def test_system_manager_cannot_read_api_password(self):
		response = self.request(
			"system_manager",
			"POST",
			"/api/method/frappe.client.get_password",
			json={"doctype": "AI API", "name": self.fixture["credential_api"], "fieldname": "api_key"},
		)
		self.assertIn(response.status_code, {401, 403})
		self.assertNotIn(self.fixture["credential"], response.text)

	def test_desk_save_preserves_hidden_credentials(self):
		name = self.fixture["editable_api"]
		for enabled in (0, 1):
			with self.subTest(enabled=enabled):
				loaded = self.request(
					"manager",
					"GET",
					"/api/method/frappe.desk.form.load.getdoc",
					params={"doctype": "AI API", "name": name},
				)
				self.assertEqual(loaded.status_code, 200)
				document = next(row for row in loaded.json()["docs"] if row["name"] == name)
				self.assertNotIn("api_key", document)
				document.update(enabled=enabled, priority=10 + enabled)
				saved = self.request(
					"manager",
					"POST",
					"/api/method/frappe.desk.form.save.savedocs",
					json={"doc": json.dumps(document), "action": "Save"},
				)
				self.assertEqual(saved.status_code, 200, saved.json().get("exc_type"))
				self.assertNotIn(self.fixture["credential"], saved.text)
				frappe.db.rollback()
				actual = get_decrypted_password("AI API", name, "api_key", raise_exception=False)
				self.assertTrue(actual == self.fixture["credential"])

	def test_authentication_failure_is_recorded_and_skipped(self):
		api = self.fixture["first_api"]
		count = len(self.fixture["attempts"])
		self.fixture["provider_status"]["/first/api/chat"] = 401
		try:
			failed_over = self.complete("manager")
			self.assertEqual(failed_over.status_code, 200)
			doc = self.request("manager", "GET", self.resource("AI API", api)).json()["data"]
			self.assertEqual(doc["health_status"], "auth_failed")
			second = self.complete("manager")
			self.assertEqual(second.status_code, 200)
			self.assertEqual(
				self.fixture["attempts"][count:],
				[
					"/first/api/chat",
					"/second/api/chat",
					"/second/api/chat",
				],
			)
		finally:
			frappe.db.rollback()
			frappe.db.set_value("AI API", api, "health_status", "healthy", update_modified=False)
			frappe.db.commit()

	def test_provider_forbidden_does_not_disable_connection(self):
		api = self.fixture["first_api"]
		count = len(self.fixture["attempts"])
		self.fixture["provider_status"]["/first/api/chat"] = 403
		self.assertEqual(self.complete("manager").json()["message"]["api"], self.fixture["second_api"])
		document = self.request("manager", "GET", self.resource("AI API", api)).json()["data"]
		self.assertNotEqual(document["health_status"], "auth_failed")
		self.fixture["provider_status"]["/first/api/chat"] = 200
		self.assertEqual(self.complete("manager").json()["message"]["api"], api)
		self.assertEqual(
			self.fixture["attempts"][count:],
			[
				"/first/api/chat",
				"/second/api/chat",
				"/first/api/chat",
			],
		)

	def test_only_ai_manager_can_change_route_data_policy(self):
		route = self.resource("AI Route", self.fixture["role_route"])
		denied = self.request("system_manager", "PUT", route, json={"data_policy": "masked"})
		self.assertEqual(denied.status_code, 403, denied.json().get("exc_type"))
		allowed = self.request("manager", "PUT", route, json={"data_policy": "masked"})
		self.assertEqual(allowed.status_code, 200, allowed.json().get("exc_type"))
		self.assertEqual(allowed.json()["data"]["data_policy"], "masked")
		restored = self.request("manager", "PUT", route, json={"data_policy": "local_only"})
		self.assertEqual(restored.status_code, 200, restored.json().get("exc_type"))

	def test_expired_cooldown_allows_candidate_again(self):
		api = self.fixture["first_api"]
		key = self._cooldown_key(api)
		count = len(self.fixture["attempts"])
		self.fixture["provider_status"]["/first/api/chat"] = 200
		frappe.cache.set(key, time() + 60, ex=60)
		self.assertEqual(self.complete("manager").json()["message"]["api"], self.fixture["second_api"])
		frappe.cache.set(key, time() - 1, ex=60)
		self.assertEqual(self.complete("manager").json()["message"]["api"], api)
		self.assertEqual(self.fixture["attempts"][count:], ["/second/api/chat", "/first/api/chat"])

	def test_locked_account_rejects_probe_without_dispatch(self):
		key = frappe.cache.make_key("model_gateway:account:" + self.fixture["second_account"])
		count = len(self.fixture["attempts"])
		with frappe.cache.lock(key, timeout=30, blocking=False):
			response = self._test_api_request("manager")
		self.assertEqual(response.status_code, 429)
		self.assertEqual(response.json()["message"]["error"], "gateway_busy")
		self.assertEqual(len(self.fixture["attempts"]), count)

	def test_external_policy_masks_without_per_message_approval(self):
		base = "https://provider.example.test"
		route = SimpleNamespace(name="fixture-route", data_policy="masked")
		identifiers = (
			"111 111 111 11",
			"1023456789",
			"TR33 0006 1005 1978 6457 8413 26",
			"4111 1111 1111 1111",
			"+90 532 123 45 67",
			"fixture@example.test",
		)
		message = " | ".join((*identifiers, "Order 12345678901234567890"))
		inbound = policy.Request([{"role": "user", "content": message}], [], None, 12)
		with patch.dict(frappe.conf, {"model_gateway_endpoints": {base: "external"}}):
			outbound = policy.outbound(base, "", route, inbound)
		adapters.complete(
			adapters.Endpoint("fixture-api", "ollama", self.fixture["provider_url"]),
			"fixture-model",
			outbound.messages,
			outbound.limit,
			tools=outbound.tools,
			schema=outbound.schema,
		)
		self.assertEqual(len(self.fixture["provider_payloads"]), 1)
		wire_payload = self.fixture["provider_payloads"][0].decode()
		self.assertEqual(wire_payload.count("[REDACTED]"), len(identifiers))
		for identifier in identifiers:
			self.assertTrue(identifier not in wire_payload)
		self.assertIn("Order 12345678901234567890", wire_payload)
		self.assertEqual(inbound.messages[0]["content"], message)

	def test_outbound_rejects_unsafe_endpoint_configurations(self):
		route = SimpleNamespace(name="fixture-route", data_policy="masked")
		request = policy.Request([{"role": "user", "content": "Fixture"}], [], None, 12)
		base = "https://provider.example.test"
		oauth_url = "https://oauth.example.test"
		cases = (
			(base, "", {}),
			("http://provider.example.test", "", {"http://provider.example.test": "external"}),
			(base, oauth_url, {base: "external", oauth_url: "local"}),
		)
		for url, token_url, settings in cases:
			with self.subTest(url=url, token_url=token_url):
				with patch.dict(frappe.conf, {"model_gateway_endpoints": settings}):
					with self.assertRaises(policy.Denied) as failure:
						policy.outbound(url, token_url, route, request)
				self.assertEqual(
					(failure.exception.status, failure.exception.code), (503, "endpoint_unavailable")
				)

	def _maintenance(self, actor, endpoint, payload):
		return self.request(actor, "POST", f"/api/method/platform_core.api.model.{endpoint}", json=payload)

	def test_resolve_usage_guest_denied(self):
		response = self._maintenance("guest", "resolve_usage", {"log": "missing", "cost": "0"})
		self.assertIn(response.status_code, {401, 403})

	def test_resolve_usage_foreign_data_denied(self):
		response = self._maintenance("regular", "resolve_usage", {"log": "missing", "cost": "0"})
		self.assertEqual(response.status_code, 403)

	def test_purge_usage_guest_denied(self):
		response = self._maintenance("guest", "purge_usage", {"dry_run": True})
		self.assertIn(response.status_code, {401, 403})

	def test_purge_usage_foreign_data_denied(self):
		response = self._maintenance("regular", "purge_usage", {"dry_run": True})
		self.assertEqual(response.status_code, 403)

	def test_second_api_quota_stops_attempt_before_provider_call(self):
		self.assertEqual(self._test_api_request("manager").status_code, 200)
		response = self.request(
			"manager",
			"PUT",
			self.resource("AI API", self.fixture["second_api"]),
			json={"requests_per_minute": 1},
		)
		self.assertEqual(response.status_code, 200)
		count = len(self.fixture["attempts"])
		self.assertEqual(self._test_api_request("manager").status_code, 429)
		self.assertEqual(len(self.fixture["attempts"]), count)
		self.assertEqual(
			self.request(
				"manager",
				"PUT",
				self.resource("AI API", self.fixture["second_api"]),
				json={"requests_per_minute": 0},
			).status_code,
			200,
		)

	def _probe_log(self):
		self.assertEqual(self._test_api_request("manager").status_code, 200)
		frappe.db.rollback()
		return frappe.db.get_value(
			"AI Usage Log", {"api": self.fixture["second_api"]}, "name", order_by="attempted_at desc"
		)

	def test_manager_can_resolve_an_unknown_attempt(self):
		log = self._probe_log()
		frappe.db.set_value("AI Usage Log", log, {"result": "unknown", "cost_known": 0})
		frappe.db.commit()
		response = self._maintenance("manager", "resolve_usage", {"log": log, "cost": 0.125})
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		frappe.db.rollback()
		record = frappe.get_doc("AI Usage Log", log)
		self.assertEqual(record.result, "resolved")
		self.assertEqual(record.cost_known, 1)
		self.assertAlmostEqual(record.cost, 0.125)
		self.assertEqual(record.resolved_by, self.fixture["users"]["manager"])
		self.assertTrue(record.resolved_at)
		self.assertTrue(record.resolution_note)

	def test_retention_preserves_old_unknown_attempts(self):
		closed, unknown = self._probe_log(), self._probe_log()
		baseline = self._maintenance("manager", "purge_usage", {"dry_run": True})
		self.assertEqual(baseline.status_code, 200, baseline.json().get("exc_type"))
		eligible = baseline.json()["message"]["eligible"]
		old = add_days(now_datetime(), -int(frappe.conf.get("model_gateway_usage_retention_days") or 365) - 1)
		frappe.db.set_value("AI Usage Log", closed, {"attempted_at": old, "result": "success"})
		frappe.db.set_value("AI Usage Log", unknown, {"attempted_at": old, "result": "unknown"})
		frappe.db.commit()
		response = self._maintenance("manager", "purge_usage", {"dry_run": True})
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(
			response.json()["message"], {"eligible": eligible + 1, "deleted": 0, "dry_run": True}
		)
		frappe.db.rollback()
		self.assertTrue(frappe.db.exists("AI Usage Log", closed))
		self.assertTrue(frappe.db.exists("AI Usage Log", unknown))
		self.assertEqual(eligible, 0, "The isolated fixture must own every record eligible for deletion")
		response = self._maintenance("manager", "purge_usage", {"dry_run": False})
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(response.json()["message"], {"eligible": 1, "deleted": 1, "dry_run": False})
		frappe.db.rollback()
		self.assertFalse(frappe.db.exists("AI Usage Log", closed))
		self.assertTrue(frappe.db.exists("AI Usage Log", unknown))

	def test_background_user_can_complete_and_guest_cannot(self):
		route = self.fixture["role_route"]
		messages = [{"role": "user", "content": "Background fixture"}]
		count = len(self.fixture["attempts"])
		current_user = frappe.session.user
		try:
			frappe.set_user(self.fixture["users"]["authorized"])
			result = gateway.complete(route, messages, [], None, 12)
			self.assertEqual(result["api"], self.fixture["second_api"])
			frappe.set_user("Guest")
			with self.assertRaises(policy.Denied):
				gateway.complete(route, messages, [], None, 12)
		finally:
			frappe.set_user(current_user)
		self.assertEqual(self.fixture["attempts"][count:], ["/second/api/chat"])

	def test_clear_api_credential_guest_denied(self):
		response = self._maintenance("guest", "clear_api_credential", {"api": self.fixture["credential_api"]})
		self.assertIn(response.status_code, {401, 403})

	def test_clear_api_credential_foreign_data_denied(self):
		response = self._maintenance(
			"regular", "clear_api_credential", {"api": self.fixture["credential_api"]}
		)
		self.assertEqual(response.status_code, 403)

	def test_manager_can_explicitly_clear_disabled_credential(self):
		name = self.fixture["clearable_api"]
		denied = self._maintenance("manager", "clear_api_credential", {"api": name})
		self.assertGreaterEqual(denied.status_code, 400)
		self.assertEqual(
			self.request("manager", "PUT", self.resource("AI API", name), json={"enabled": 0}).status_code,
			200,
		)
		cleared = self._maintenance("manager", "clear_api_credential", {"api": name})
		self.assertEqual(cleared.status_code, 200)
		self.assertNotIn(self.fixture["credential"], cleared.text)
		frappe.db.rollback()
		self.assertFalse(get_decrypted_password("AI API", name, "api_key", raise_exception=False))

	def test_tenant_manager_can_create_multiple_providers(self):
		resource = self.resource("AI Provider")
		names = []
		for adapter in ("openai", "ollama"):
			response = self.request(
				"manager",
				"POST",
				resource,
				json={"provider_name": f"HTTP fixture {uuid4().hex}", "adapter": adapter, "enabled": 0},
			)
			self.assertEqual(response.status_code, 200)
			names.append(response.json()["data"]["name"])
			self.addCleanup(self.delete_provider, names[-1])
		self.assertNotEqual(*names)

	def test_zero_budget_stops_probe_before_provider_call(self):
		api = self.resource("AI API", self.fixture["second_api"])
		account = self.resource("AI Account", self.fixture["second_account"])
		self.assertEqual(
			self.request("manager", "PUT", api, json={"requests_per_minute": 0}).status_code, 200
		)
		self.assertEqual(
			self.request(
				"manager",
				"PUT",
				account,
				json={"has_monthly_budget": 1, "monthly_budget": 0},
			).status_code,
			200,
		)
		count = len(self.fixture["attempts"])
		self.assertEqual(self._test_api_request("manager").status_code, 503)
		self.assertEqual(len(self.fixture["attempts"]), count)

	def delete_provider(self, name):
		response = self.request("manager", "DELETE", self.resource("AI Provider", name))
		self.assertIn(response.status_code, {200, 202, 204})
