"""Production handlers ignore synthetic request-local command registrations."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from platform_core.api import mobile


class MobileApiRegistryTest(TestCase):
	def test_test_configuration_cannot_replace_production_registries(self):
		identity = SimpleNamespace(
			account="fixture@example.test", site="test-mobile.localhost", principal="fixture", scope="mobile"
		)
		frappe = SimpleNamespace(
			conf={"allow_tests": True, "mobile_cursor_key": "fixture-key" * 4},
			local=SimpleNamespace(
				mobile_commands={"synthetic": object()},
				mobile_projections={"synthetic": object()},
				mobile_inventories={"synthetic": object()},
			),
		)
		body = {"installation_id": str(uuid4())}
		with (
			patch.object(mobile, "frappe", frappe),
			patch.object(mobile, "MobileStore"),
			patch.object(mobile, "_lock_mobile_account"),
			patch.object(mobile, "_require_enabled_user"),
			patch.object(mobile, "_require_recent_activity"),
			patch.object(mobile, "push") as push,
			patch.object(mobile, "pull") as pull,
		):
			mobile._push(identity, dict(body, operations=[]))
			mobile._pull(identity, body)
		self.assertIs(push.call_args.args[1], mobile.COMMANDS)
		self.assertIs(pull.call_args.args[1], mobile.PROJECTIONS)
		self.assertIs(pull.call_args.kwargs["inventories"], mobile.INVENTORIES)
