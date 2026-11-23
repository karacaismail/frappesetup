"""Check provider definitions, connection saving and the live connection check."""

import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password

from platform_core.model_gateway import adapters, connections
from platform_core.model_gateway.adapters import Endpoint, GatewayError
from platform_core.model_gateway.policy import Denied

CATALOG_PATH = "/api/method/platform_core.api.model.provider_catalog"
SAVE_PATH = "/api/method/platform_core.api.model.save_connection"
CHECK_PATH = "/api/method/platform_core.api.model.check_connection"
MODEL_LISTS = {
	"/v1/models": {"data": [{"id": "fixture-a"}, {"id": "fixture-b"}]},
	"/v1beta/models": {"models": [{"name": "fixture-a"}]},
	"/api/tags": {"models": [{"name": "fixture-a"}, {"name": "fixture-b"}, {"name": "fixture-c"}]},
}


class ListHandler(BaseHTTPRequestHandler):
	def log_message(self, *_args):
		pass

	def do_GET(self):
		self.server.requests.append((self.command, self.path, dict(self.headers)))
		status = self.server.status
		body = MODEL_LISTS.get(self.path, {"error": "unknown fixture path"}) if status == 200 else {}
		if status == 200 and self.path not in MODEL_LISTS:
			status = 404
		payload = json.dumps(body).encode()
		self.send_response(status)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(payload)))
		self.end_headers()
		self.wfile.write(payload)

	def do_POST(self):
		length = int(self.headers.get("Content-Length") or 0)
		self.rfile.read(length)
		self.server.requests.append((self.command, self.path, dict(self.headers)))
		payload = json.dumps(
			{
				"choices": [{"message": {"content": "fixture"}}],
				"usage": {"prompt_tokens": 1, "completion_tokens": 1},
			}
		).encode()
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(payload)))
		self.end_headers()
		self.wfile.write(payload)


class FakeProvider:
	"""Loopback model-list server. No real provider receives a request."""

	def __enter__(self):
		self.server = ThreadingHTTPServer(("127.0.0.1", 0), ListHandler)
		self.server.requests = []
		self.server.status = 200
		self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02})
		self.thread.start()
		self.url = f"http://127.0.0.1:{self.server.server_port}"
		return self

	def __exit__(self, *_exc):
		self.server.shutdown()
		self.thread.join()
		self.server.server_close()

	@property
	def requests(self):
		return self.server.requests

	def endpoint(self, adapter, auth="none", secret="", **extra):
		return Endpoint(
			"fixture", adapter, self.url, auth, secret, kind="local", addresses=("127.0.0.1",), **extra
		)


def _credential():
	return f"test-only-{uuid4().hex}"


class CatalogTests(unittest.TestCase):
	def test_catalog_offers_the_three_required_providers_in_the_llm_category(self):
		catalog = connections.provider_catalog_data()
		self.assertIn("ai_llm", {category["id"] for category in catalog["categories"]})
		by_id = {provider["id"]: provider for provider in catalog["providers"]}
		for provider in ("openai", "gemini", "anthropic"):
			with self.subTest(provider=provider):
				self.assertEqual(by_id[provider]["category"], "ai_llm")
				secrets = [field for field in by_id[provider]["fields"] if field["kind"] == "secret"]
				self.assertEqual([field["name"] for field in secrets], ["api_key"])
				self.assertTrue(secrets[0]["required"])

	def test_public_catalog_hides_storage_details(self):
		with patch.object(connections.policy, "require_user"):
			catalog = connections.provider_catalog()
		text = json.dumps(catalog)
		for hidden in ("target", "adapter", "default_url", "api.api_key"):
			with self.subTest(hidden=hidden):
				self.assertNotIn(f'"{hidden}"', text)
		for provider in catalog["providers"]:
			names = [field["name"] for field in provider["common_fields"]]
			self.assertEqual(names, ["account_name", "api_name"])
			for field in provider["fields"]:
				self.assertIn(field["scope"], {"account", "api"})

	def test_catalog_requires_a_manager(self):
		with patch.object(connections.policy, "require_user", side_effect=frappe.PermissionError) as check:
			with self.assertRaises(frappe.PermissionError):
				connections.provider_catalog()
		check.assert_called_once_with(managers_only=True)

	def test_catalog_has_no_model_names(self):
		# O-13: model names live only in AI Model records.
		catalog = connections.provider_catalog_data()
		for provider in catalog["providers"]:
			self.assertNotIn("model", {key.lower() for key in provider})
			for field in provider["fields"]:
				self.assertNotIn("model", field["name"])

	def test_invalid_catalog_definitions_are_rejected(self):
		valid = connections.provider_catalog_data()
		connections.validate_catalog(copy.deepcopy(valid))

		def broken(change):
			data = copy.deepcopy(valid)
			change(data)
			return data

		def first_field(data):
			return data["providers"][0]["fields"][0]

		cases = {
			"unknown adapter": lambda data: data["providers"][0].update(adapter="unknown"),
			"unknown category": lambda data: data["providers"][0].update(category="missing"),
			"unknown target": lambda data: first_field(data).update(target="api.priority"),
			"secret outside the encrypted field": lambda data: first_field(data).update(
				target="api.base_url"
			),
			"plain text in the encrypted field": lambda data: first_field(data).update(kind="text"),
			"duplicate provider": lambda data: data["providers"].append(copy.deepcopy(data["providers"][0])),
			"duplicate field": lambda data: data["providers"][0]["fields"].append(
				copy.deepcopy(first_field(data))
			),
			"common field name": lambda data: first_field(data).update(name="api_name"),
			"extra key": lambda data: first_field(data).update(extra=True),
			"credential without secret field": lambda data: data["providers"][0].update(
				fields=[field for field in data["providers"][0]["fields"] if field["kind"] != "secret"]
			),
			"no address": lambda data: data["providers"][0].update(default_url=""),
			"plain HTTP default": lambda data: data["providers"][0].update(
				default_url="http://fixture.example"
			),
		}
		for name, change in cases.items():
			with self.subTest(case=name), self.assertRaises(ValueError):
				connections.validate_catalog(broken(change))


class FieldTests(unittest.TestCase):
	def setUp(self):
		self.openai = connections.provider_definition("openai")
		self.ollama = connections.provider_definition("ollama")

	def assert_field_error(self, definition, fields, expected, *, new_account=True):
		with self.assertRaises(Denied) as failure:
			connections.parse_fields(definition, fields, new_account=new_account)
		self.assertEqual((failure.exception.status, failure.exception.code), (400, "invalid_fields"))
		self.assertEqual(failure.exception.fields, expected)

	def test_unknown_provider_is_rejected(self):
		for provider in ("missing", "", None, 5, "OpenAI"):
			with self.subTest(provider=provider), self.assertRaises(Denied) as failure:
				connections.provider_definition(provider)
			self.assertEqual(failure.exception.code, "unknown_provider")

	def test_valid_fields_map_to_their_records(self):
		credential = _credential()
		values = connections.parse_fields(
			self.openai,
			{"api_key": credential, "organization_id": "org-fixture", "project_id": ""},
			new_account=True,
		)
		self.assertEqual(values, {"api.api_key": credential, "account.organization_id": "org-fixture"})

	def test_missing_required_field(self):
		self.assert_field_error(self.openai, {"organization_id": "org-fixture"}, ["api_key"])

	def test_unknown_and_malformed_fields(self):
		credential = _credential()
		self.assert_field_error(self.openai, {"api_key": credential, "priority": "9"}, ["priority"])
		self.assert_field_error(self.openai, {"api_key": 12}, ["api_key"])
		self.assert_field_error(self.openai, {"api_key": f" {credential}"}, ["api_key"])
		self.assert_field_error(self.openai, {"api_key": "x" * 4097}, ["api_key"])
		self.assert_field_error(
			self.openai, {"api_key": credential, "organization_id": "org\nfixture"}, ["organization_id"]
		)
		self.assert_field_error(self.ollama, {"base_url": "ftp://fixture.example"}, ["base_url"])
		self.assert_field_error(self.ollama, {"base_url": "http://fixture.example/?q=1"}, ["base_url"])
		with self.assertRaises(Denied) as failure:
			connections.parse_fields(self.openai, ["api_key"], new_account=True)
		self.assertEqual(failure.exception.code, "invalid_request")

	def test_account_fields_need_a_new_account(self):
		self.assert_field_error(
			self.openai,
			{"api_key": _credential(), "organization_id": "org-fixture"},
			["organization_id"],
			new_account=False,
		)

	def test_check_status_codes(self):
		expected = {
			"authentication": "invalid_credentials",
			"forbidden": "permission_denied",
			"rate_limit": "quota_exceeded",
			"connect_failed": "network_error",
			"timeout": "network_error",
			"endpoint_unavailable": "network_error",
			"upstream": "provider_error",
			"rejected": "provider_error",
			"invalid_response": "provider_error",
			"configuration": "configuration_error",
		}
		for code, status in expected.items():
			with self.subTest(code=code):
				self.assertEqual(connections.check_status(code), status)


class ModelListTests(unittest.TestCase):
	def test_each_protocol_lists_models_with_its_own_credential_header(self):
		credential = _credential()
		cases = (
			("openai", "api_key", "/v1/models", "Authorization", f"Bearer {credential}", 2),
			("anthropic", "api_key", "/v1/models", "x-api-key", credential, 2),
			("gemini", "api_key", "/v1beta/models", "x-goog-api-key", credential, 1),
			("ollama", "none", "/api/tags", None, None, 3),
		)
		with FakeProvider() as provider:
			for adapter, auth, path, header, value, count in cases:
				with self.subTest(adapter=adapter):
					provider.requests.clear()
					secret = credential if auth != "none" else ""
					self.assertEqual(adapters.list_models(provider.endpoint(adapter, auth, secret)), count)
					[(method, sent_path, headers)] = provider.requests
					self.assertEqual((method, sent_path), ("GET", path))
					lowered = {key.lower(): item for key, item in headers.items()}
					if header:
						self.assertEqual(lowered[header.lower()], value)
					if adapter == "anthropic":
						self.assertIn("anthropic-version", lowered)
					if auth == "none":
						self.assertNotIn("authorization", lowered)

	def test_openai_account_identifiers_are_sent_as_headers(self):
		with FakeProvider() as provider:
			endpoint = provider.endpoint(
				"openai", "api_key", _credential(), organization="org-fixture", project="proj-fixture"
			)
			adapters.list_models(endpoint)
			adapters.complete(endpoint, "fixture-model", [{"role": "user", "content": "fixture"}], 8)
			for _method, _path, headers in provider.requests:
				lowered = {key.lower(): item for key, item in headers.items()}
				self.assertEqual(lowered["openai-organization"], "org-fixture")
				self.assertEqual(lowered["openai-project"], "proj-fixture")

	def test_identifiers_stay_out_of_other_protocols(self):
		with FakeProvider() as provider:
			adapters.list_models(
				provider.endpoint("anthropic", "api_key", _credential(), organization="org-fixture")
			)
			[(_method, _path, headers)] = provider.requests
			self.assertNotIn("openai-organization", {key.lower() for key in headers})

	def test_provider_statuses_become_fixed_codes(self):
		cases = {401: "authentication", 403: "forbidden", 429: "rate_limit", 500: "upstream", 404: "rejected"}
		with FakeProvider() as provider:
			for status, code in cases.items():
				with self.subTest(status=status), self.assertRaises(GatewayError) as failure:
					provider.server.status = status
					adapters.list_models(provider.endpoint("openai", "api_key", _credential()))
				self.assertEqual(failure.exception.code, code)
				self.assertFalse(failure.exception.may_be_billed)

	def test_unexpected_body_is_an_invalid_response(self):
		with FakeProvider() as provider:
			endpoint = provider.endpoint("gemini", "api_key", _credential())
			with patch.dict(MODEL_LISTS, {"/v1beta/models": {"models": "fixture"}}):
				with self.assertRaises(GatewayError) as failure:
					adapters.list_models(endpoint)
		self.assertEqual(failure.exception.code, "invalid_response")

	def test_closed_port_is_a_connection_failure(self):
		with FakeProvider() as provider:
			endpoint = provider.endpoint("ollama")
		with self.assertRaises(GatewayError) as failure:
			adapters.list_models(endpoint, timeout=1, connect_timeout=1)
		self.assertEqual(failure.exception.code, "connect_failed")

	def test_public_destination_rules_still_apply(self):
		endpoint = Endpoint("fixture", "ollama", "http://127.0.0.1:9")
		with self.assertRaises(GatewayError) as failure:
			adapters.list_models(endpoint)
		self.assertEqual(failure.exception.code, "endpoint_unavailable")


class ConnectionRecordTests(IntegrationTestCase):
	"""Save and check through the service layer with real records on the test site."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = uuid4().hex[:10]
		frappe.set_user("Administrator")
		cls.users = {}
		for actor, roles in (("manager", ["PLT AI Manager"]), ("desk", [])):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": f"connection-{actor}-{suffix}@example.test",
					"first_name": f"Connection fixture {actor}",
					"send_welcome_email": 0,
					"user_type": "System User",
					"roles": [{"role": role} for role in roles],
				}
			).insert()
			cls.users[actor] = user.name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for user in cls.users.values():
			frappe.delete_doc("User", user, force=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user(self.users["manager"])
		self.provider = self.enterContext(FakeProvider())
		self.created = []

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for doctype, name in reversed(self.created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True)
		frappe.db.commit()

	def approve(self):
		return patch.dict(
			frappe.conf,
			{"model_gateway_endpoints": {self.provider.url: {"kind": "local", "addresses": ["127.0.0.1"]}}},
		)

	def save(self, provider, fields, **names):
		names.setdefault("api_name", f"Fixture connection {uuid4().hex[:8]}")
		if "account" not in names:
			names.setdefault("account_name", f"Fixture account {uuid4().hex[:8]}")
		result = connections.save_connection(provider, fields=fields, **names)
		self.created.append(("PLT AI API", result["api"]))
		if "account" not in names:
			self.created.insert(0, ("PLT AI Account", result["account"]))
		frappe.db.commit()
		return result

	def test_save_stores_the_secret_only_encrypted(self):
		credential = _credential()
		result = self.save("openai_compatible", {"base_url": self.provider.url, "api_key": credential})
		self.assertEqual(result["connection_status"], "not_checked")
		self.assertEqual(set(result), {"provider", "account", "api", "connection_status"})
		self.assertNotIn(credential, json.dumps(result))
		stored = frappe.db.get_value(
			"PLT AI API", result["api"], ["api_key", "auth_type", "base_url"], as_dict=True
		)
		self.assertNotEqual(stored.api_key, credential)
		self.assertEqual((stored.auth_type, stored.base_url), ("bearer", self.provider.url))
		self.assertEqual(get_decrypted_password("PLT AI API", result["api"], "api_key"), credential)
		self.assertNotIn(
			credential, json.dumps(frappe.get_doc("PLT AI API", result["api"]).as_dict(), default=str)
		)
		self.assertEqual(
			frappe.db.get_value("PLT AI Provider", result["provider"], "catalog_provider"),
			"openai_compatible",
		)

	def test_save_reuses_the_provider_record_and_an_existing_account(self):
		first = self.save("ollama", {"base_url": self.provider.url})
		second = self.save("ollama", {"base_url": self.provider.url}, account=first["account"])
		self.assertEqual(first["provider"], second["provider"])
		self.assertEqual(first["account"], second["account"])
		self.assertNotEqual(first["api"], second["api"])

	def test_account_of_another_provider_is_rejected(self):
		ollama = self.save("ollama", {"base_url": self.provider.url})
		with self.assertRaises(Denied) as failure:
			connections.save_connection(
				"openai_compatible",
				api_name="Mismatched",
				fields={"base_url": self.provider.url, "api_key": _credential()},
				account=ollama["account"],
			)
		self.assertEqual((failure.exception.code, failure.exception.fields), ("invalid_fields", ["account"]))

	def test_name_rules(self):
		for names in (
			{"api_name": "Fixture"},
			{"api_name": "Fixture", "account": "missing", "account_name": "Both"},
			{"api_name": "", "account_name": "Fixture"},
			{"api_name": "x" * 141, "account_name": "Fixture"},
		):
			with self.subTest(names=names), self.assertRaises(Denied) as failure:
				connections.save_connection("ollama", fields={"base_url": self.provider.url}, **names)
			self.assertEqual(failure.exception.status, 400)

	def test_save_and_check_need_a_manager(self):
		saved = self.save("ollama", {"base_url": self.provider.url})
		frappe.set_user(self.users["desk"])
		with self.assertRaises(frappe.PermissionError):
			connections.save_connection(
				"ollama", api_name="Denied", account_name="Denied", fields={"base_url": self.provider.url}
			)
		with self.assertRaises(frappe.PermissionError):
			connections.check_connection(saved["api"])
		self.assertEqual(self.provider.requests, [])

	def test_check_records_a_connected_result(self):
		saved = self.save("ollama", {"base_url": self.provider.url})
		frappe.db.set_value("PLT AI API", saved["api"], "health_status", "unhealthy")
		frappe.db.commit()
		with self.approve():
			result = connections.check_connection(saved["api"])
		self.assertEqual(
			(result["api"], result["status"], result["models_visible"]), (saved["api"], "connected", 3)
		)
		record = frappe.db.get_value(
			"PLT AI API",
			saved["api"],
			["connection_status", "connection_checked_at", "health_status"],
			as_dict=True,
		)
		self.assertEqual((record.connection_status, record.health_status), ("connected", "healthy"))
		self.assertIsNotNone(record.connection_checked_at)
		self.assertEqual([request[:2] for request in self.provider.requests], [("GET", "/api/tags")])

	def test_check_reports_an_invalid_key_without_the_key(self):
		credential = _credential()
		saved = self.save("openai_compatible", {"base_url": self.provider.url, "api_key": credential})
		self.provider.server.status = 401
		with self.approve():
			result = connections.check_connection(saved["api"])
		self.assertEqual(result["status"], "invalid_credentials")
		self.assertIsNone(result["models_visible"])
		self.assertNotIn(credential, json.dumps(result))
		record = frappe.db.get_value("PLT AI API", saved["api"], ["connection_status", "health_status"])
		self.assertEqual(record, ("invalid_credentials", "auth_failed"))
		[(_method, _path, headers)] = self.provider.requests
		self.assertEqual(headers.get("Authorization"), f"Bearer {credential}")

	def test_check_reports_quota_and_network_failures(self):
		saved = self.save("ollama", {"base_url": self.provider.url})
		self.provider.server.status = 429
		with self.approve():
			self.assertEqual(connections.check_connection(saved["api"])["status"], "quota_exceeded")
		frappe.db.commit()
		with self.approve(), patch.object(connections, "CHECK_TIMEOUT", 1):
			self.provider.__exit__(None, None, None)
			result = connections.check_connection(saved["api"])
		self.assertEqual(result["status"], "network_error")
		# Restart the loopback server so tearDown can stop it again.
		self.provider = self.enterContext(FakeProvider())

	def test_unapproved_address_is_not_contacted(self):
		saved = self.save("ollama", {"base_url": self.provider.url})
		with patch.dict(frappe.conf, {"model_gateway_endpoints": {}}):
			result = connections.check_connection(saved["api"])
		self.assertEqual(result["status"], "endpoint_not_approved")
		self.assertEqual(self.provider.requests, [])
		self.assertEqual(
			frappe.db.get_value("PLT AI API", saved["api"], "connection_status"), "endpoint_not_approved"
		)

	def test_check_needs_a_clean_transaction_and_a_valid_name(self):
		with self.assertRaises(Denied) as failure:
			connections.check_connection("")
		self.assertEqual(failure.exception.code, "invalid_request")
		with self.assertRaises(frappe.PermissionError):
			connections.check_connection("missing-fixture-api")

	def test_changing_the_credential_resets_the_check(self):
		saved = self.save("openai_compatible", {"base_url": self.provider.url, "api_key": _credential()})
		with self.approve():
			connections.check_connection(saved["api"])
		frappe.db.commit()
		frappe.set_user("Administrator")
		api = frappe.get_doc("PLT AI API", saved["api"])
		api.api_key = _credential()
		api.save()
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("PLT AI API", saved["api"], "connection_status"), "not_checked")
