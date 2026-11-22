"""Check bounded selection reads and stable route target validation."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from platform_core.model_gateway import gateway


class TargetQueryTests(unittest.TestCase):
	def setUp(self):
		self.names = [
			SimpleNamespace(api=f"api-{index}", model=f"model-{index}")
			for index in range(gateway.MAX_TARGETS)
		]
		self.rows = {
			"PLT AI API": {
				item.api: SimpleNamespace(name=item.api, account="account", allowed_models="[]")
				for item in self.names
			},
			"PLT AI Model": {
				item.model: SimpleNamespace(name=item.model, provider="provider", model_id=item.model)
				for item in self.names
			},
			"PLT AI Account": {"account": SimpleNamespace(name="account", provider="provider")},
			"PLT AI Provider": {"provider": SimpleNamespace(name="provider")},
		}

	def _complete(self, targets):
		route = SimpleNamespace(targets=targets)

		def get_doc(doctype, name):
			if doctype == "PLT AI Route":
				return route
			try:
				return self.rows[doctype][name]
			except KeyError:
				raise gateway.frappe.DoesNotExistError from None

		def get_all(doctype, *, filters, fields, **kwargs):
			self.assertNotIn("*", fields)
			self.assertNotIn("api_key", fields)
			self.assertIn("name", fields)
			operator, names = filters["name"]
			self.assertEqual(operator, "in")
			self.assertEqual(len(set(names)), len(names))
			# The database can return rows in a different order than the route.
			return [row for name, row in reversed(self.rows[doctype].items()) if name in names]

		with (
			patch.object(gateway.frappe, "get_doc", side_effect=get_doc) as docs,
			patch.object(gateway.frappe, "get_all", side_effect=get_all) as batches,
			patch.object(gateway.policy, "require_user"),
			patch.object(gateway.policy, "require_route") as authorization,
			patch.object(gateway, "_require_clean_transaction"),
			patch.object(gateway, "monotonic", return_value=10),
			patch.object(gateway, "_dispatch", return_value={"ok": True}) as dispatch,
		):
			result = gateway.complete("route", [{"role": "user", "content": "fixture"}])
		authorization.assert_called_once_with(route)
		self.assertEqual(dispatch.call_args.args[3], 70)
		self.assertEqual(result, {"ok": True})
		return docs, batches, dispatch

	def test_selects_twelve_targets_with_four_bounded_queries(self):
		docs, batches, dispatch = self._complete(self.names)
		docs.assert_called_once_with("PLT AI Route", "route")
		self.assertEqual(
			[call.args[0] for call in batches.call_args_list],
			["PLT AI API", "PLT AI Model", "PLT AI Account", "PLT AI Provider"],
		)
		self.assertEqual(
			[(target.api.name, target.model.name) for target in dispatch.call_args.args[1]],
			[(item.api, item.model) for item in self.names],
		)

	def test_empty_route_keeps_dispatch_behavior_without_target_queries(self):
		docs, batches, dispatch = self._complete([])
		docs.assert_called_once_with("PLT AI Route", "route")
		batches.assert_not_called()
		self.assertEqual(dispatch.call_args.args[1], [])

	def test_preserves_first_missing_target_error(self):
		del self.rows["PLT AI API"]["api-0"]
		self.rows["PLT AI Model"]["model-1"].provider = "elsewhere"
		with self.assertRaises(gateway.frappe.PermissionError):
			self._complete(self.names)

	def test_rejects_disallowed_model_before_missing_later_target(self):
		self.rows["PLT AI API"]["api-0"].allowed_models = '["another-model"]'
		del self.rows["PLT AI API"]["api-1"]
		with self.assertRaises(gateway.Denied) as failure:
			self._complete(self.names)
		self.assertEqual((failure.exception.status, failure.exception.code), (400, "invalid_target"))

	def test_invalid_target_identifier_retains_invalid_request_error(self):
		self.names[0].api = None
		with self.assertRaises(gateway.Denied) as failure:
			self._complete(self.names)
		self.assertEqual((failure.exception.status, failure.exception.code), (400, "invalid_request"))

	def test_denied_route_never_reads_registry_batches(self):
		route = SimpleNamespace(targets=self.names)
		with (
			patch.object(gateway, "_require_clean_transaction"),
			patch.object(gateway.frappe, "get_doc", return_value=route),
			patch.object(gateway.frappe, "get_all") as batches,
			patch.object(gateway.policy, "require_user"),
			patch.object(gateway.policy, "require_route", side_effect=gateway.frappe.PermissionError),
			self.assertRaises(gateway.frappe.PermissionError),
		):
			gateway.complete("route", [{"role": "user", "content": "fixture"}])
		batches.assert_not_called()

	def test_attempt_checks_selected_records_again_before_reserving(self):
		selected = SimpleNamespace(api=SimpleNamespace(name="api"), model=SimpleNamespace(name="model"))
		refreshed = SimpleNamespace(api=SimpleNamespace(enabled=False))
		with (
			patch.object(gateway, "_choose", side_effect=[[(None, selected)], []]),
			patch.object(gateway, "_target", return_value=refreshed) as load,
			patch.object(gateway, "_reserve") as reserve,
			self.assertRaises(gateway.Denied) as failure,
		):
			gateway._dispatch(Mock(), [selected], Mock(), float("inf"))
		load.assert_called_once_with("api", "model")
		reserve.assert_not_called()
		self.assertEqual((failure.exception.status, failure.exception.code), (503, "provider_unavailable"))
