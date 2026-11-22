"""Regression coverage for provider registry persistence and credentials."""

from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.client import get_password
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password


def _insert(doctype, **values):
	return frappe.get_doc({"doctype": doctype, **values}).insert()


class TestGatewayRegistry(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.provider = _insert(
			"AI Provider", provider_name=f"Registry fixture {uuid4().hex}", adapter="openai"
		)
		self.account = _insert("AI Account", provider=self.provider.name, account_name="Registry fixture")

	def _api(self, **values):
		return _insert(
			"AI API",
			account=self.account.name,
			api_name="Registry fixture",
			auth_type="api_key",
			api_key="local-fixture-credential",
			base_url="https://provider.example.test",
			**values,
		)

	def _assert_credential(self, api, value):
		self.assertEqual(get_decrypted_password("AI API", api.name, "api_key", raise_exception=False), value)

	def test_native_password_endpoint_denies_even_system_manager(self):
		api = self._api()
		with self.assertRaises(frappe.PermissionError):
			get_password("AI API", api.name, "api_key")

	def test_form_save_preserves_enabled_credential(self):
		api = self._api()
		form = frappe.get_doc("AI API", api.name).as_dict()
		self.assertNotIn("api_key", form)
		form["priority"] = 2
		frappe.get_doc(form).save()
		self._assert_credential(api, "local-fixture-credential")

	def test_form_save_preserves_disabled_credential_and_allows_rotation(self):
		api = self._api(enabled=0)
		form = frappe.get_doc("AI API", api.name).as_dict()
		form["api_key"] = ""
		form["priority"] = 2
		saved = frappe.get_doc(form).save()
		self._assert_credential(api, "local-fixture-credential")
		saved.api_key = "local-rotated-credential"
		saved.save()
		self._assert_credential(api, "local-rotated-credential")

	def test_secret_clear_requires_disabled_connection(self):
		from platform_core.model_gecidi.doctype.ai_api.ai_api import clear_api_credential

		api = self._api()
		with self.assertRaises(frappe.ValidationError):
			clear_api_credential(api.name)
		self._assert_credential(api, "local-fixture-credential")
		api.enabled = 0
		api.save()
		clear_api_credential(api.name)
		self._assert_credential(api, None)
		self.assertFalse(frappe.db.get_value("AI API", api.name, "api_key"))

	def test_rejects_unsafe_registry_urls(self):
		for field, url in (
			("base_url", "https://user:pass@provider.example.test"),
			("base_url", "https://provider.example.test?redirect=secret"),
			("base_url", "https://provider.example.test:99999"),
			("oauth_token_url", "http://provider.example.test"),
		):
			with self.subTest(field=field, url=url), self.assertRaises(frappe.ValidationError):
				api = self._api(enabled=0)
				api.set(field, url)
				api.save()
		with self.assertRaises(frappe.ValidationError):
			_insert("AI Provider", provider_name="Invalid URL", adapter="openai", default_url="ftp://host")

	def test_rejects_zero_model_context(self):
		with self.assertRaises(frappe.ValidationError):
			_insert("AI Model", provider=self.provider.name, model_id="registry-fixture", context_size=0)

	def test_model_speed_defaults_to_thirty_output_tokens_per_second(self):
		model = _insert(
			"AI Model", provider=self.provider.name, model_id="registry-speed-fixture", context_size=128
		)
		self.assertEqual(model.reload().get("output_tokens_per_second"), 30)

	def test_model_speed_must_be_positive(self):
		for speed in (0, -1):
			with self.subTest(speed=speed), self.assertRaises(frappe.ValidationError):
				_insert(
					"AI Model",
					provider=self.provider.name,
					model_id="registry-speed-fixture",
					context_size=128,
					output_tokens_per_second=speed,
				)

	def test_public_completion_forwards_gateway_arguments(self):
		from platform_core.model_gecidi.api import complete

		messages = [{"role": "user", "content": "Hello"}]
		with patch("platform_core.model_gecidi.gateway.complete", return_value={"text": "Hello"}) as gateway:
			self.assertEqual(complete("fixture", messages), {"text": "Hello"})
		gateway.assert_called_once_with("fixture", messages, tools=None, schema=None, limit=1024)

	def _route_fields(self):
		model = _insert(
			"AI Model", provider=self.provider.name, model_id="registry-route-fixture", context_size=128
		)
		api = self._api()
		return {
			"route_name": f"Registry route {uuid4().hex}",
			"targets": frappe.as_json([{"api": api.name, "model": model.name}]),
		}

	def _role_user(self, role):
		return _insert(
			"User",
			email=f"registry-{uuid4().hex}@example.test",
			first_name="Registry fixture",
			send_welcome_email=0,
			roles=[{"role": role}],
		).name

	def test_route_defaults_to_local_only_for_system_manager(self):
		fields = self._route_fields()
		user = self._role_user("System Manager")
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user(user)
		route = _insert("AI Route", **fields)
		self.assertEqual(route.data_policy, "local_only")

	def test_only_ai_manager_can_select_masked_route_policy(self):
		fields = self._route_fields()
		system_manager = self._role_user("System Manager")
		ai_manager = self._role_user("AI Manager")
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user(system_manager)
		with self.assertRaises(frappe.PermissionError):
			_insert("AI Route", data_policy="masked", **fields)
		route = _insert("AI Route", data_policy="local_only", **fields)
		with self.assertRaises(frappe.PermissionError):
			route.data_policy = "masked"
			route.save()
		frappe.set_user(ai_manager)
		new_route = _insert(
			"AI Route", data_policy="masked", **{**fields, "route_name": fields["route_name"] + " approved"}
		)
		self.assertEqual(new_route.data_policy, "masked")
		route = frappe.get_doc("AI Route", route.name)
		route.data_policy = "masked"
		route.save()
		frappe.set_user(system_manager)
		route = frappe.get_doc("AI Route", route.name)
		route.enabled = 0
		route.save()
		self.assertEqual(route.data_policy, "masked")
		route.data_policy = "local_only"
		route.save()
