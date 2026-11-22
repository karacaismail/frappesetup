"""Verify the gateway HTTP boundary with Frappe's whitelist wrapper active."""

import inspect
import unittest
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import Mock, patch

import frappe

from platform_core.api import model


class ModelHttpTypesTests(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe.local, "request", object(), create=True))
		self.enterContext(patch.object(frappe.local, "response", frappe._dict(), create=True))
		self.enterContext(patch.object(frappe.local, "db", Mock(), create=True))
		self.enterContext(patch.object(model.policy, "require_session"))
		self.enterContext(patch.object(model.policy, "require_user"))
		self.enterContext(patch.object(model.gateway, "_require_clean_transaction"))

	def test_every_whitelisted_operation_declares_its_boundary_types(self):
		for endpoint in (
			model.complete,
			model.test_api,
			model.resolve_usage,
			model.purge_usage,
			model.clear_api_credential,
		):
			with self.subTest(endpoint=endpoint.__name__):
				self.assertEqual(
					set(get_type_hints(endpoint)), {*inspect.signature(endpoint).parameters, "return"}
				)

	def test_whitelist_leaves_invalid_input_to_gateway_policy(self):
		messages = [{"role": "user", "content": "Fixture"}]
		for endpoint, arguments, error in (
			(model.complete, ("route", [], None, None, 12), "invalid_request"),
			(model.complete, ("route", messages, None, None, "12"), "invalid_request"),
			(model.complete, ("route", messages, None, None, True), "invalid_request"),
			(model.test_api, (False, "model"), "invalid_request"),
			(model.resolve_usage, ("log", 0.125, "USD"), "invalid_cost"),
			(model.resolve_usage, ("log", "0.125", "usd"), "invalid_currency"),
			(model.purge_usage, ("false",), "invalid_request"),
			(model.purge_usage, (0,), "invalid_request"),
			(model.clear_api_credential, (False,), "invalid_request"),
		):
			with self.subTest(endpoint=endpoint.__name__, arguments=arguments):
				self.assertEqual(endpoint(*arguments), {"error": error})
				self.assertEqual(frappe.local.response.http_status_code, 400)

	def test_http_denial_rolls_back_only_the_current_transaction(self):
		denial = model.policy.Denied(400, "invalid_request")
		with patch.object(model.maintenance, "purge_usage", side_effect=denial):
			self.assertEqual(model.purge_usage(), {"error": "invalid_request"})

		frappe.db.rollback.assert_called_once_with(chain=True)
		frappe.db.commit.assert_not_called()
		self.assertEqual(frappe.local.response.http_status_code, 400)

	def test_route_permission_failure_uses_frappe_error(self):
		route = SimpleNamespace(enabled=True, required_role="AI Caller")
		with (
			patch.object(frappe, "get_roles", return_value=["Other"]),
			self.assertRaises(frappe.PermissionError),
		):
			model.policy.require_route(route)
