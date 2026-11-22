"""Verify delivery acknowledgment failure handling."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import frappe
from frappe.utils import CallbackManager

from platform_core.mobil import identity_sync_client, sessions


class SessionDeliveryTest(TestCase):
	def setUp(self):
		self.targets = (("session", "subject"),)
		self.db = Mock(after_commit=CallbackManager())
		self.logger = Mock()
		self.enterContext(
			patch.object(
				sessions,
				"frappe",
				SimpleNamespace(
					db=self.db,
					logger=self.logger,
					QueryDeadlockError=frappe.QueryDeadlockError,
					QueryTimeoutError=frappe.QueryTimeoutError,
				),
			)
		)
		self.send = self.enterContext(patch.object(sessions, "send_session_revocations", return_value=()))

	def test_transient_acknowledgment_errors_roll_back_the_acknowledgment(self):
		for method, error in (
			(self.db.set_value, frappe.QueryDeadlockError),
			(self.db.commit, frappe.QueryTimeoutError),
		):
			with self.subTest(error=error.__name__):
				method.side_effect = error
				sessions._deliver_committed(self.targets)
				method.side_effect = None
				self.db.rollback.assert_called_once_with()
				self.logger.return_value.warning.assert_called_once()
				self.db.reset_mock()
				self.logger.reset_mock()

	def test_acknowledgment_timeout_preserves_callbacks_from_the_committed_transaction(self):
		self.db.set_value.side_effect = frappe.QueryTimeoutError
		self.db.rollback.side_effect = self.db.after_commit.reset
		later = Mock()
		self.db.after_commit.add(lambda: sessions._deliver_committed(self.targets))
		self.db.after_commit.add(later)

		self.db.after_commit.run()

		later.assert_called_once_with()

	def test_forbidden_response_clears_pending_without_removing_local_revocation(self):
		self.send.side_effect = identity_sync_client.send_session_revocations
		with (
			patch.object(identity_sync_client, "frappe", SimpleNamespace(logger=self.logger)),
			patch.object(identity_sync_client, "_configured_url", return_value="https://sync.example.test"),
			patch.object(identity_sync_client, "_service_bearer", return_value="fixture-bearer"),
			patch.object(
				identity_sync_client._OPENER, "open", side_effect=HTTPError("", 403, "Forbidden", None, None)
			),
		):
			sessions._deliver_committed(self.targets)
		self.db.set_value.assert_called_once_with(
			sessions.REVOKED_SESSION,
			{"name": ["in", [sessions._session_key("session")]]},
			"delivery_pending",
			0,
		)
		self.db.commit.assert_called_once_with()
		self.db.delete.assert_not_called()

	def test_unexpected_delivery_error_surfaces(self):
		self.send.side_effect = TypeError("Unexpected delivery value")
		with self.assertRaises(TypeError):
			sessions._deliver_committed(self.targets)
		self.db.set_value.assert_not_called()
		self.db.commit.assert_not_called()

	def test_unexpected_acknowledgment_error_surfaces(self):
		self.db.set_value.side_effect = TypeError("Unexpected database argument")
		with self.assertRaises(TypeError):
			sessions._deliver_committed(self.targets)
		self.db.commit.assert_not_called()
