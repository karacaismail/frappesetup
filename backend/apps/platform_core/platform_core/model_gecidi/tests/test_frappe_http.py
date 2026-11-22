"""HTTP acceptance checks against a disposable, pre-seeded Frappe test site."""

import json
import os
import unittest
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

import requests

FIXTURE_PATH = os.environ.get("MODEL_GATEWAY_HTTP_FIXTURE")


@unittest.skipUnless(FIXTURE_PATH, "Frappe HTTP test fixture is unavailable")
class FrappeHTTPTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fixture = json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))
		cls.base = cls.fixture["base_url"].rstrip("/")
		if urlsplit(cls.base).hostname not in {"127.0.0.1", "::1", "localhost"}:
			raise ValueError("Use a loopback tunnel to the disposable Frappe site")

	def request(self, actor, method, path, **kwargs):
		response = requests.request(
			method,
			self.base + path,
			headers=self.fixture["headers"][actor],
			timeout=15,
			allow_redirects=False,
			**kwargs,
		)
		return response

	def resource(self, doctype, name=""):
		path = "/api/resource/" + quote(doctype, safe="")
		if name:
			path += "/" + quote(name, safe="")
		return path

	def test_regular_user_cannot_list_or_read_provider_credentials(self):
		for name in ("", self.fixture["first_api"]):
			with self.subTest(detail=bool(name)):
				response = self.request("regular", "GET", self.resource("AI API", name))
				self.assertEqual(response.status_code, 403)

	def test_manager_can_read_api_without_getting_secret(self):
		name = self.fixture["first_api"]
		detail = self.request("manager", "GET", self.resource("AI API", name))
		self.assertEqual(detail.status_code, 200)
		self.assertEqual(detail.json()["data"]["name"], name)
		listing = self.request(
			"manager",
			"GET",
			self.resource("AI API"),
			params={"fields": json.dumps(["name", "api_key"])},
		)
		self.assertIn(listing.status_code, {200, 403, 417})
		for response in (detail, listing):
			self.assertFalse(self.fixture["fake_api_secret"] in response.text)

	def test_route_falls_back_to_another_account_and_api(self):
		route = self.fixture["fallback_route"]
		response = self.request(
			"manager",
			"POST",
			"/api/method/platform_core.api.model.complete",
			json={"route": route, "messages": [{"role": "user", "content": "fixture"}], "limit": 12},
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["message"]["api"], self.fixture["second_api"])
		usage = self.request(
			"manager",
			"GET",
			self.resource("AI Usage Log"),
			params={"filters": json.dumps({"route": route}), "fields": '["api","account"]'},
		)
		self.assertEqual(usage.status_code, 200)
		attempts = {(record["api"], record["account"]) for record in usage.json()["data"]}
		expected = {
			(self.fixture["first_api"], self.fixture["first_account"]),
			(self.fixture["second_api"], self.fixture["second_account"]),
		}
		self.assertTrue(expected <= attempts)

	def test_tenant_manager_can_create_multiple_providers(self):
		resource = self.resource("AI Provider")
		names = []
		for adapter in ("openai", "ollama"):
			name = f"HTTP fixture {uuid4().hex}"
			response = self.request(
				"manager",
				"POST",
				resource,
				json={"provider_name": name, "adapter": adapter, "enabled": 0},
			)
			self.assertEqual(response.status_code, 200)
			names.append(response.json()["data"]["name"])
			self.addCleanup(self.delete_provider, names[-1])
		self.assertNotEqual(*names)

	def delete_provider(self, name):
		response = self.request("manager", "DELETE", self.resource("AI Provider", name))
		self.assertIn(response.status_code, {200, 202, 204})
