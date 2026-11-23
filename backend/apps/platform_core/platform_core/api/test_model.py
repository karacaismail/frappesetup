"""Real HTTP checks run by the disposable model gateway fixture."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

import frappe
from frappe.utils import add_days, now_datetime
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from platform_core.model_gateway import adapters, gateway, policy


class TestModelHTTP(unittest.TestCase):
	fixture = None
	D6_ACTORS = ("guest", "desk_no_gateway_role", "regular", "manager", "system_manager")

	@classmethod
	def setUpClass(cls):
		if cls.fixture is None:
			raise unittest.SkipTest("Run the disposable Frappe HTTP fixture")
		from platform_core.model_gateway.tests.contract_validation import GatewayContract

		cls.gateway_contract = GatewayContract()

	def setUp(self):
		self.fixture["provider_payloads"].clear()
		for api in (self.fixture["first_api"], self.fixture["second_api"]):
			frappe.cache.delete(self._cooldown_key(api))
			frappe.db.delete("PLT AI Usage Log", {"api": api})
		# Connection form endpoints count requests per user. Each test starts with fresh counters.
		frappe.cache.delete_keys("rl:platform_core.model_gateway.connections.")
		frappe.db.commit()
		self.fixture["provider_status"]["/first/api/chat"] = 429

	def _cooldown_key(self, api):
		return frappe.cache.make_key(f"model_gateway:cooldown:{api}")

	def request(self, actor, method, path, **kwargs):
		session = self.fixture["sessions"][actor]
		if actor in {"oauth", "api_key", "manager_key"}:
			session.cookies.clear()
		response = session.request(
			method, self.fixture["base"] + path, timeout=15, allow_redirects=False, **kwargs
		)
		if path in self.gateway_contract.spec["paths"]:
			self.gateway_contract.validate_response(path, method, response.status_code, response.json())
		return response

	def resource(self, doctype, name=""):
		path = "/api/resource/" + quote(doctype, safe="")
		if name:
			path += "/" + quote(name, safe="")
		return path

	def complete(self, actor, route=None, *, limit=12):
		return self.request(
			actor,
			"POST",
			"/api/method/platform_core.api.model.complete",
			json={
				"route": route or self.fixture["route"],
				"messages": [{"role": "user", "content": "fixture message for failover"}],
				"limit": limit,
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
		self.assertEqual(self.complete("guest").status_code, 403)

	def test_complete_foreign_data_denied(self):
		self.assertEqual(self.complete("regular").status_code, 403)

	def test_test_api_guest_denied(self):
		self.assertEqual(self._test_api_request("guest").status_code, 403)

	def test_test_api_foreign_data_denied(self):
		self.assertEqual(self._test_api_request("regular").status_code, 403)

	def test_non_manager_desk_user_receives_native_permission_error(self):
		response = self._test_api_request("authorized")
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json().get("exc_type"), "PermissionError")

	def test_regular_user_cannot_list_or_read_provider_credentials(self):
		for name in ("", self.fixture["credential_api"]):
			with self.subTest(detail=bool(name)):
				response = self.request("regular", "GET", self.resource("PLT AI API", name))
				self.assertEqual(response.status_code, 403)

	def test_manager_can_read_api_without_getting_secret(self):
		name = self.fixture["credential_api"]
		detail = self.request("manager", "GET", self.resource("PLT AI API", name))
		self.assertEqual(detail.status_code, 200)
		self.assertEqual(detail.json()["data"]["name"], name)
		self.assertNotIn("api_key", detail.json()["data"])
		listing = self.request(
			"manager",
			"GET",
			self.resource("PLT AI API"),
			params={"fields": json.dumps(["name", "api_key"]), "filters": json.dumps({"name": name})},
		)
		self.assertEqual(listing.status_code, 200)
		self.assertNotIn("api_key", listing.json()["data"][0])
		document = self.request(
			"manager",
			"GET",
			"/api/method/frappe.client.get",
			params={"doctype": "PLT AI API", "name": name},
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
			self.resource("PLT AI Usage Log"),
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

	def test_route_rejects_native_oauth_bearer_after_authentication(self):
		identity = self.request("oauth", "GET", "/api/method/frappe.auth.get_logged_user")
		self.assertEqual(identity.status_code, 200)
		self.assertEqual(identity.json()["message"], self.fixture["users"]["manager"])
		count = len(self.fixture["attempts"])
		for response in (self.complete("oauth"), self._test_api_request("oauth")):
			self.assertEqual(response.status_code, 401)
			self.assertEqual(response.json()["message"]["error"], "authentication_required")
		self.assertEqual(len(self.fixture["attempts"]), count)

	def test_manager_operations_reject_native_api_key(self):
		identity = self.request("manager_key", "GET", "/api/method/frappe.auth.get_logged_user")
		self.assertEqual(identity.status_code, 200)
		self.assertEqual(identity.json()["message"], self.fixture["users"]["manager"])
		checks = {
			"test_api": {"api": self.fixture["second_api"], "model": self.fixture["model"]},
			"resolve_usage": {"log": "missing-fixture-log", "cost": "0", "currency": "USD"},
			"purge_usage": {"dry_run": True},
			"clear_api_credential": {"api": self.fixture["clearable_api"]},
			"provider_catalog": {},
			"save_connection": self._connection_payload(),
			"check_connection": {"api": self.fixture["second_api"]},
		}
		for endpoint, payload in checks.items():
			with self.subTest(endpoint=endpoint):
				response = self._maintenance("manager_key", endpoint, payload)
				self.assertEqual(response.status_code, 401)
				self.assertEqual(response.json()["message"]["error"], "authentication_required")

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
			json={"doctype": "PLT AI API", "name": self.fixture["credential_api"], "fieldname": "api_key"},
		)
		self.assertEqual(response.status_code, 403)
		self.assertNotIn(self.fixture["credential"], response.text)

	def test_desk_save_preserves_hidden_credentials(self):
		name = self.fixture["editable_api"]
		for enabled in (0, 1):
			with self.subTest(enabled=enabled):
				loaded = self.request(
					"manager",
					"GET",
					"/api/method/frappe.desk.form.load.getdoc",
					params={"doctype": "PLT AI API", "name": name},
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
				actual = get_decrypted_password("PLT AI API", name, "api_key", raise_exception=False)
				self.assertTrue(actual == self.fixture["credential"])

	def test_authentication_failure_is_recorded_and_skipped(self):
		api = self.fixture["first_api"]
		count = len(self.fixture["attempts"])
		self.fixture["provider_status"]["/first/api/chat"] = 401
		try:
			failed_over = self.complete("manager")
			self.assertEqual(failed_over.status_code, 200)
			doc = self.request("manager", "GET", self.resource("PLT AI API", api)).json()["data"]
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
			frappe.db.set_value("PLT AI API", api, "health_status", "healthy", update_modified=False)
			frappe.db.commit()

	def test_provider_forbidden_does_not_disable_connection(self):
		api = self.fixture["first_api"]
		count = len(self.fixture["attempts"])
		self.fixture["provider_status"]["/first/api/chat"] = 403
		self.assertEqual(self.complete("manager").json()["message"]["api"], self.fixture["second_api"])
		document = self.request("manager", "GET", self.resource("PLT AI API", api)).json()["data"]
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
		route = self.resource("PLT AI Route", self.fixture["role_route"])
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
			"+90 200 000 00 00",
			"fixture@example.test",
		)
		message = " | ".join((*identifiers, "Order 12345678901234567890"))
		inbound = policy.Request([{"role": "user", "content": message}], [], None, 12)
		with patch.dict(frappe.conf, {"model_gateway_endpoints": {base: "external"}}):
			outbound = policy.outbound(base, "", route, inbound)
		adapters.complete(
			adapters.Endpoint(
				"fixture-api",
				"ollama",
				self.fixture["provider_url"],
				kind="local",
				addresses=("127.0.0.1",),
			),
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

	def _assert_d6_access(self, operation, request, *, allowed=("manager", "system_manager")):
		for actor in self.D6_ACTORS:
			with self.subTest(operation=operation, actor=actor):
				response = request(actor)
				print(f"D6 {operation} {actor} {response.status_code}", flush=True)
				expected = 200 if actor in allowed else 403
				self.assertEqual(response.status_code, expected, response.json().get("exc_type"))
				if expected == 403:
					self.assertEqual(response.json().get("exc_type"), "PermissionError")

	def test_d6_fixture_identities(self):
		users = self.fixture["users"]
		actor_types = {
			"desk_no_gateway_role": "System User",
			"regular": "Website User",
			"manager": "System User",
			"system_manager": "System User",
		}
		for actor, user_type in actor_types.items():
			with self.subTest(actor=actor):
				self.assertEqual(frappe.db.get_value("User", users[actor], "user_type"), user_type)
		route_role = frappe.db.get_value("PLT AI Route", self.fixture["role_route"], "required_role")
		desk_roles = set(frappe.get_roles(users["desk_no_gateway_role"]))
		self.assertTrue(desk_roles.isdisjoint({route_role, "PLT AI Manager", "System Manager"}))
		self.assertIn("PLT AI Manager", frappe.get_roles(users["manager"]))
		self.assertNotIn("System Manager", frappe.get_roles(users["manager"]))
		self.assertIn("System Manager", frappe.get_roles(users["system_manager"]))

	def test_d6_complete(self):
		self._assert_d6_access("complete", lambda actor: self.complete(actor, self.fixture["role_route"]))

	def test_d6_test_api(self):
		self._assert_d6_access("test_api", self._test_api_request)

	def test_d6_resolve_usage(self):
		def request(actor):
			log = self._probe_log()
			frappe.db.set_value("PLT AI Usage Log", log, {"result": "unknown", "cost_known": 0})
			frappe.db.commit()
			return self._maintenance(actor, "resolve_usage", {"log": log, "cost": "0.125", "currency": "USD"})

		self._assert_d6_access("resolve_usage", request)

	def test_d6_reconcile_stale_pending(self):
		def request(actor):
			log = self._probe_log()
			frappe.db.set_value(
				"PLT AI Usage Log", log, {"result": "pending", "attempted_at": add_days(now_datetime(), -1)}
			)
			frappe.db.commit()
			return self._maintenance(actor, "reconcile_stale_pending", {})

		self._assert_d6_access("reconcile_stale_pending", request)

	def test_d6_purge_preview(self):
		self._assert_d6_access(
			"purge_usage_preview",
			lambda actor: self._maintenance(actor, "purge_usage", {"dry_run": True}),
			allowed=("system_manager",),
		)

	def test_d6_purge_execute(self):
		log = self._probe_log()
		frappe.db.set_value("PLT AI Usage Log", log, "attempted_at", add_days(now_datetime(), -366))
		frappe.db.commit()
		preview = self._maintenance("system_manager", "purge_usage", {"dry_run": True}).json()["message"]
		self.assertEqual(preview["targets"], [log])
		self._assert_d6_access(
			"purge_usage_execute",
			lambda actor: self._maintenance(
				actor, "purge_usage", {"dry_run": False, "preview_token": preview["preview_token"]}
			),
			allowed=("system_manager",),
		)
		frappe.db.rollback()
		audit = frappe.db.exists(
			"Activity Log",
			{"subject": "Model gateway usage logs purged", "user": self.fixture["users"]["system_manager"]},
		)
		if audit:
			self.addCleanup(self._delete_activity_log, audit)

	def test_d6_clear_api_credential(self):
		api_name = self.fixture["d6_clearable_api"]

		def request(actor):
			frappe.db.set_value("PLT AI API", api_name, "enabled", 0)
			set_encrypted_password("PLT AI API", api_name, self.fixture["credential"], "api_key")
			frappe.db.commit()
			return self._maintenance(actor, "clear_api_credential", {"api": api_name})

		self._assert_d6_access("clear_api_credential", request)

	def _connection_payload(self, provider="ollama", fields=None):
		return {
			"provider": provider,
			"account_name": f"HTTP connection account {uuid4().hex[:8]}",
			"api_name": f"HTTP connection {uuid4().hex[:8]}",
			"fields": {"base_url": self.fixture["provider_url"]} if fields is None else fields,
		}

	def _remove_connection(self, saved):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for doctype, name in (("PLT AI API", saved["api"]), ("PLT AI Account", saved["account"])):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True)
		frappe.db.commit()

	def _save_connection(self, actor, payload=None):
		response = self._maintenance(actor, "save_connection", payload or self._connection_payload())
		if response.status_code == 200:
			self.addCleanup(self._remove_connection, response.json()["message"])
		return response

	def test_provider_catalog_guest_denied(self):
		self.assertEqual(self._maintenance("guest", "provider_catalog", {}).status_code, 403)

	def test_provider_catalog_foreign_data_denied(self):
		response = self._maintenance("regular", "provider_catalog", {})
		self.assertEqual(response.status_code, 403)
		self.assertNotIn("api_key", response.text)

	def test_save_connection_guest_denied(self):
		self.assertEqual(self._save_connection("guest").status_code, 403)

	def test_save_connection_foreign_data_denied(self):
		existing = {**self._connection_payload(), "account": self.fixture["second_account"]}
		existing.pop("account_name")
		for actor in ("regular", "desk_no_gateway_role"):
			with self.subTest(actor=actor):
				self.assertEqual(self._save_connection(actor, existing).status_code, 403)

	def test_check_connection_guest_denied(self):
		response = self._maintenance("guest", "check_connection", {"api": self.fixture["second_api"]})
		self.assertEqual(response.status_code, 403)

	def test_check_connection_foreign_data_denied(self):
		requests_before = len(self.fixture["list_requests"])
		response = self._maintenance("regular", "check_connection", {"api": self.fixture["credential_api"]})
		self.assertEqual(response.status_code, 403)
		self.assertNotIn(self.fixture["credential"], response.text)
		self.assertEqual(len(self.fixture["list_requests"]), requests_before)

	def test_d6_provider_catalog(self):
		self._assert_d6_access(
			"provider_catalog", lambda actor: self._maintenance(actor, "provider_catalog", {})
		)

	def test_d6_save_connection(self):
		self._assert_d6_access("save_connection", self._save_connection)

	def test_d6_check_connection(self):
		saved = self._save_connection("manager").json()["message"]
		self._assert_d6_access(
			"check_connection",
			lambda actor: self._maintenance(actor, "check_connection", {"api": saved["api"]}),
		)

	def test_manager_adds_and_checks_a_connection_without_seeing_the_key(self):
		credential = f"test-only-{uuid4().hex}"
		payload = self._connection_payload(
			"openai_compatible", {"base_url": self.fixture["provider_url"], "api_key": credential}
		)
		catalog = self._maintenance("manager", "provider_catalog", {})
		self.assertEqual(catalog.status_code, 200)
		self.assertIn("openai_compatible", {item["id"] for item in catalog.json()["message"]["providers"]})
		saved = self._save_connection("manager", payload)
		self.assertEqual(saved.status_code, 200, saved.text)
		self.assertNotIn(credential, saved.text)
		api = saved.json()["message"]["api"]
		requests_before = len(self.fixture["list_requests"])
		checked = self._maintenance("manager", "check_connection", {"api": api})
		self.assertEqual(checked.status_code, 200, checked.text)
		self.assertEqual(checked.json()["message"]["status"], "connected")
		self.assertEqual(checked.json()["message"]["models_visible"], 2)
		self.assertNotIn(credential, checked.text)
		[(path, authorization)] = self.fixture["list_requests"][requests_before:]
		self.assertEqual((path, authorization), ("/second/v1/models", f"Bearer {credential}"))
		record = self.request("manager", "GET", self.resource("PLT AI API", api))
		self.assertEqual(record.json()["data"]["connection_status"], "connected")
		self.assertNotIn(credential, record.text)

	def test_connection_endpoints_answer_gateway_busy_over_the_rate_limit(self):
		saved = self._save_connection("manager").json()["message"]
		user = self.fixture["users"]["manager"]
		requests_before = len(self.fixture["list_requests"])
		for endpoint, payload in (
			("check_connection", {"api": saved["api"]}),
			("save_connection", self._connection_payload()),
		):
			with self.subTest(endpoint=endpoint):
				counter = f"rl:platform_core.model_gateway.connections.{endpoint}:{user}"
				frappe.cache.setex(frappe.cache.make_key(counter) + b":60", 60, 10)
				response = self._maintenance("manager", endpoint, payload)
				self.assertEqual(response.status_code, 429)
				self.assertEqual(response.json()["message"], {"error": "gateway_busy"})
				self.assertNotIn("_server_messages", response.json())
		self.assertEqual(len(self.fixture["list_requests"]), requests_before)

	def test_check_connection_reports_an_invalid_key(self):
		saved = self._save_connection(
			"manager",
			self._connection_payload(
				"openai_compatible",
				{"base_url": self.fixture["provider_url"], "api_key": f"test-only-{uuid4().hex}"},
			),
		).json()["message"]
		self.fixture["provider_status"]["/second/v1/models"] = 401
		self.addCleanup(self.fixture["provider_status"].pop, "/second/v1/models", None)
		checked = self._maintenance("manager", "check_connection", {"api": saved["api"]})
		self.assertEqual(checked.status_code, 200)
		self.assertEqual(checked.json()["message"]["status"], "invalid_credentials")

	def test_save_connection_names_the_invalid_fields(self):
		response = self._save_connection(
			"manager",
			self._connection_payload("openai_compatible", {"base_url": self.fixture["provider_url"]}),
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["message"], {"error": "invalid_fields", "fields": ["api_key"]})

	def test_resolve_usage_guest_denied(self):
		response = self._maintenance(
			"guest", "resolve_usage", {"log": "missing", "cost": "0", "currency": "USD"}
		)
		self.assertEqual(response.status_code, 403)

	def test_resolve_usage_foreign_data_denied(self):
		response = self._maintenance(
			"regular", "resolve_usage", {"log": "missing", "cost": "0", "currency": "USD"}
		)
		self.assertEqual(response.status_code, 403)

	def test_purge_usage_guest_denied(self):
		response = self._maintenance("guest", "purge_usage", {"dry_run": True})
		self.assertEqual(response.status_code, 403)

	def test_reconcile_stale_pending_guest_denied(self):
		response = self._maintenance("guest", "reconcile_stale_pending", {})
		self.assertEqual(response.status_code, 403)

	def test_reconcile_stale_pending_foreign_data_denied(self):
		for actor in ("regular", "authorized"):
			with self.subTest(actor=actor):
				response = self._maintenance(actor, "reconcile_stale_pending", {})
				self.assertEqual(response.status_code, 403)
				self.assertEqual(response.json().get("exc_type"), "PermissionError")

	def test_manager_can_reconcile_a_stale_pending_reservation(self):
		log = self._probe_log()
		frappe.db.set_value(
			"PLT AI Usage Log",
			log,
			{
				"result": "pending",
				"attempted_at": add_days(now_datetime(), -1),
				"reservation_known": 1,
				"reserved_cost": "0.125",
			},
		)
		frappe.db.commit()
		response = self._maintenance("manager", "reconcile_stale_pending", {})
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(response.json()["message"], {"closed": 1, "targets": [log]})
		frappe.db.rollback()
		record = frappe.get_doc("PLT AI Usage Log", log)
		self.assertEqual(
			(record.result, record.failure_code, record.reserved_cost), ("unknown", "pending_recovery", 0.125)
		)

	def test_purge_usage_foreign_data_denied(self):
		response = self._maintenance("regular", "purge_usage", {"dry_run": True})
		self.assertEqual(response.status_code, 403)

	def test_second_api_quota_stops_attempt_before_provider_call(self):
		self.assertEqual(self._test_api_request("manager").status_code, 200)
		response = self.request(
			"manager",
			"PUT",
			self.resource("PLT AI API", self.fixture["second_api"]),
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
				self.resource("PLT AI API", self.fixture["second_api"]),
				json={"requests_per_minute": 0},
			).status_code,
			200,
		)

	def _probe_log(self):
		self.assertEqual(self._test_api_request("manager").status_code, 200)
		frappe.db.rollback()
		return frappe.db.get_value(
			"PLT AI Usage Log", {"api": self.fixture["second_api"]}, "name", order_by="attempted_at desc"
		)

	def test_manager_can_resolve_an_unknown_attempt(self):
		log = self._probe_log()
		frappe.db.set_value("PLT AI Usage Log", log, {"result": "unknown", "cost_known": 0})
		frappe.db.commit()
		note = "Verified using a fixture invoice."
		request = {"log": log, "cost": "0.125000001", "currency": "USD", "note": note}
		for changes, error in (
			({"cost": 0.125}, "invalid_cost"),
			({"cost": "1e-3"}, "invalid_cost"),
			({"cost": "0.0000000001"}, "invalid_cost"),
			({"currency": "usd"}, "invalid_currency"),
			({"currency": "EUR"}, "currency_mismatch"),
		):
			with self.subTest(error=error, changes=changes):
				response = self._maintenance("manager", "resolve_usage", {**request, **changes})
				self.assertEqual(response.status_code, 400)
				self.assertEqual(response.json()["message"]["error"], error)
		response = self._maintenance("manager", "resolve_usage", request)
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(
			response.json()["message"],
			{"name": log, "result": "resolved", "cost": "0.125000001", "currency": "USD"},
		)
		frappe.db.rollback()
		record = frappe.get_doc("PLT AI Usage Log", log)
		self.assertEqual(record.result, "resolved")
		self.assertEqual(record.cost_known, 1)
		self.assertEqual(str(record.cost), "0.125000001")
		self.assertEqual(record.resolved_by, self.fixture["users"]["manager"])
		self.assertTrue(record.resolved_at)
		self.assertEqual(record.resolution_note, note)
		self.assertEqual(record.previous_result, "unknown")

	def test_retention_preserves_old_unknown_attempts(self):
		closed, unknown = self._probe_log(), self._probe_log()
		baseline = self._maintenance("system_manager", "purge_usage", {"dry_run": True})
		self.assertEqual(baseline.status_code, 200, baseline.json().get("exc_type"))
		eligible = baseline.json()["message"]["eligible"]
		old = add_days(now_datetime(), -366)
		frappe.db.set_value("PLT AI Usage Log", closed, {"attempted_at": old, "result": "success"})
		frappe.db.set_value("PLT AI Usage Log", unknown, {"attempted_at": old, "result": "unknown"})
		frappe.db.commit()
		response = self._maintenance("system_manager", "purge_usage", {"dry_run": True})
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		preview = response.json()["message"]
		self.assertEqual(
			preview,
			{
				"eligible": eligible + 1,
				"deleted": 0,
				"dry_run": True,
				"targets": [closed],
				"preview_token": preview["preview_token"],
			},
		)
		frappe.db.rollback()
		self.assertTrue(frappe.db.exists("PLT AI Usage Log", closed))
		self.assertTrue(frappe.db.exists("PLT AI Usage Log", unknown))
		self.assertEqual(eligible, 0, "The isolated fixture must own every record eligible for deletion")
		audit_filters = {
			"reference_doctype": "PLT AI Usage Log",
			"subject": "Model gateway usage logs purged",
			"user": self.fixture["users"]["system_manager"],
		}
		self.assertFalse(frappe.db.exists("Activity Log", audit_filters))
		without_preview = self._maintenance("system_manager", "purge_usage", {"dry_run": False})
		self.assertEqual(without_preview.status_code, 400)
		self.assertEqual(without_preview.json()["message"]["error"], "preview_required")
		response = self._maintenance(
			"system_manager", "purge_usage", {"dry_run": False, "preview_token": preview["preview_token"]}
		)
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(
			response.json()["message"],
			{"eligible": 1, "deleted": 1, "dry_run": False, "targets": [closed], "preview_token": None},
		)
		frappe.db.rollback()
		self.assertFalse(frappe.db.exists("PLT AI Usage Log", closed))
		audit = frappe.db.exists("Activity Log", audit_filters)
		self.assertTrue(audit)
		self.addCleanup(self._delete_activity_log, audit)
		self.assertTrue(frappe.db.exists("PLT AI Usage Log", unknown))

	def test_purge_rejects_an_ai_manager_for_preview_and_execution(self):
		for dry_run in (True, False):
			with self.subTest(dry_run=dry_run):
				response = self._maintenance("manager", "purge_usage", {"dry_run": dry_run})
				self.assertEqual(response.status_code, 403)
				self.assertEqual(response.json().get("exc_type"), "PermissionError")

	def _delete_activity_log(self, name):
		frappe.db.delete("Activity Log", {"name": name})
		frappe.db.commit()

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
		self.assertEqual(response.status_code, 403)

	def test_clear_api_credential_foreign_data_denied(self):
		response = self._maintenance(
			"regular", "clear_api_credential", {"api": self.fixture["credential_api"]}
		)
		self.assertEqual(response.status_code, 403)

	def test_manager_can_explicitly_clear_disabled_credential(self):
		name = self.fixture["clearable_api"]
		denied = self._maintenance("manager", "clear_api_credential", {"api": name})
		self.assertEqual(denied.status_code, 417)
		self.assertEqual(
			self.request("manager", "PUT", self.resource("PLT AI API", name), json={"enabled": 0}).status_code,
			200,
		)
		cleared = self._maintenance("manager", "clear_api_credential", {"api": name})
		self.assertEqual(cleared.status_code, 200)
		self.assertNotIn(self.fixture["credential"], cleared.text)
		frappe.db.rollback()
		self.assertFalse(get_decrypted_password("PLT AI API", name, "api_key", raise_exception=False))
		comment = frappe.db.get_value(
			"Comment",
			{
				"reference_doctype": "PLT AI API",
				"reference_name": name,
				"comment_type": "Info",
				"owner": self.fixture["users"]["manager"],
			},
			"content",
			order_by="creation desc",
		)
		self.assertTrue(comment)
		self.assertNotIn(self.fixture["credential"], comment)

	def test_tenant_manager_can_create_multiple_providers(self):
		resource = self.resource("PLT AI Provider")
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
		api = self.resource("PLT AI API", self.fixture["second_api"])
		account = self.resource("PLT AI Account", self.fixture["second_account"])
		self.addCleanup(
			self._restore_fields,
			"PLT AI Account",
			self.fixture["second_account"],
			{
				"has_monthly_budget": 0,
				"monthly_budget": 0,
			},
		)
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

	def _restore_fields(self, doctype, name, fields):
		frappe.db.set_value(doctype, name, fields)
		frappe.db.commit()

	def test_output_limit_that_cannot_fit_is_rejected_before_reservation(self):
		count = len(self.fixture["attempts"])
		response = self.complete("manager", self.fixture["role_route"], limit=4096)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["message"]["error"], "output_limit_exceeds_deadline")
		self.assertEqual(len(self.fixture["attempts"]), count)
		frappe.db.rollback()
		self.assertEqual(frappe.db.count("PLT AI Usage Log", {"api": self.fixture["second_api"]}), 0)

	def _complete_concurrently(self, *, budget, expected_second_status):
		account = self.fixture["second_account"]
		model = self.fixture["model"]
		self.addCleanup(
			self._restore_fields,
			"PLT AI Account",
			account,
			{"has_monthly_budget": 0, "monthly_budget": 0},
		)
		self.addCleanup(
			self._restore_fields,
			"PLT AI Model",
			model,
			{"prices_known": 0, "input_price": 0, "output_price": 0},
		)
		frappe.db.set_value("PLT AI Account", account, {"has_monthly_budget": 1, "monthly_budget": budget})
		frappe.db.set_value("PLT AI Model", model, {"prices_known": 1, "input_price": 0, "output_price": 1000})
		frappe.db.commit()

		first_dispatched, release_first, second_dispatched = Event(), Event(), Event()

		def gate(path):
			if path != "/second/api/chat":
				return
			if first_dispatched.is_set():
				second_dispatched.set()
			else:
				first_dispatched.set()
				release_first.wait(8)

		server = self.fixture["provider_server"]
		server.provider_gate = gate
		try:
			with ThreadPoolExecutor(2) as pool:
				first = pool.submit(self.complete, "manager", self.fixture["role_route"])
				try:
					self.assertTrue(first_dispatched.wait(5), "First request never reached the provider")
					second = pool.submit(self.complete, "authorized", self.fixture["role_route"])
					second_response = second.result(timeout=5)
					self.assertEqual(second_response.status_code, expected_second_status)
					self.assertEqual(second_dispatched.is_set(), expected_second_status == 200)
					if expected_second_status == 503:
						self.assertEqual(second_response.json()["message"]["error"], "provider_unavailable")
				finally:
					release_first.set()
				self.assertEqual(first.result(timeout=5).status_code, 200)
		finally:
			server.provider_gate = None

	def test_same_account_can_dispatch_two_concurrent_calls_with_sufficient_budget(self):
		# Each 12-token reservation costs USD 0.012 at USD 1000 per million output tokens.
		self._complete_concurrently(budget=0.024, expected_second_status=200)

	def test_same_account_rejects_second_concurrent_call_when_budget_is_reserved(self):
		self._complete_concurrently(budget=0.012, expected_second_status=503)

	def delete_provider(self, name):
		response = self.request("manager", "DELETE", self.resource("PLT AI Provider", name))
		self.assertEqual(response.status_code, 202)
