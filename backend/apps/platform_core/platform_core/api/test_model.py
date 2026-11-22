"""Real HTTP checks run by the disposable model gateway fixture."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

import frappe

from platform_core.model_gateway import policy


class TestModelHTTP(unittest.TestCase):
	fixture = None

	@classmethod
	def setUpClass(cls):
		if cls.fixture is None:
			raise unittest.SkipTest("Run the disposable Frappe HTTP fixture")

	def request(self, actor, method, path, **kwargs):
		session = self.fixture["sessions"][actor]
		if actor == "agent":
			session.cookies.clear()
		return session.request(
			method, self.fixture["base"] + path, timeout=15, allow_redirects=False, **kwargs
		)

	def resource(self, doctype, name=""):
		path = "/api/resource/" + quote(doctype, safe="")
		if name:
			path += "/" + quote(name, safe="")
		return path

	def complete(self, actor):
		return self.request(
			actor,
			"POST",
			"/api/method/platform_core.api.model.complete",
			json={
				"route": self.fixture["route"],
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

	def test_route_with_agent_token_is_scoped_and_metered(self):
		count = len(self.fixture["attempts"])
		self.assertIn(self._test_api_request("agent").status_code, {401, 403})
		override = self.request(
			"agent",
			"POST",
			"/api/method/platform_core.api.model.complete",
			json={"cmd": "platform_core.api.model.test_api"},
		)
		self.assertIn(override.status_code, {401, 403})
		mixed = self.request(
			"manager",
			"POST",
			"/api/method/platform_core.api.model.complete",
			headers={"Authorization": self.fixture["sessions"]["agent"].headers["Authorization"]},
			json={
				"route": self.fixture["route"],
				"messages": [{"role": "user", "content": "fixture"}],
			},
		)
		self.assertIn(mixed.status_code, {401, 403})
		self.assertEqual(len(self.fixture["attempts"]), count)
		response = self.complete("agent")
		self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
		self.assertEqual(response.json()["message"]["api"], self.fixture["second_api"])
		self.assertEqual(self.complete("agent").status_code, 429)
		self.assertEqual(self.fixture["attempts"][count:], ["/second/api/chat"])

	def test_external_policy_requires_an_approved_masked_payload(self):
		base = "https://provider.example.test"
		route = SimpleNamespace(name="fixture-route", data_policy="masked")
		approved = policy.Request([{"role": "user", "content": "[REDACTED]"}], [], None, 12)
		email = policy.Request([{"role": "user", "content": "fixture@example.test"}], [], None, 12)
		unapproved = policy.Request([{"role": "user", "content": "Unreviewed personal data"}], [], None, 12)
		settings = {
			"model_gateway_endpoints": {base: "external"},
			"model_gateway_external_payloads": {route.name: [policy.payload_digest(approved)]},
		}
		with patch.dict(frappe.conf, settings):
			self.assertEqual(policy.outbound(base, "", route, email), approved)
			with self.assertRaises(policy.Denied) as failure:
				policy.outbound(base, "", route, unapproved)
			self.assertEqual(failure.exception.status, 403)
			route.data_policy = "local_only"
			with self.assertRaises(policy.Denied) as failure:
				policy.outbound(base, "", route, email)
			self.assertEqual(failure.exception.status, 403)

	def test_second_api_quota_stops_attempt_before_provider_call(self):
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
