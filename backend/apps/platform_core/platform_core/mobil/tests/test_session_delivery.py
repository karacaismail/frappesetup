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

	def test_missing_remote_subject_logs_only_fixed_text(self):
		self.db.get_values.return_value = []
		with patch.object(sessions, "insert_metadata") as insert:
			sessions.revoke_after_commit([("private-session", None)])
		self.logger.return_value.warning.assert_called_once_with(
			"Mobile session closure is pending because the Keycloak subject is unavailable."
		)
		self.assertEqual(insert.call_args.kwargs["delivery_pending"], 1)
		self.send.assert_not_called()

	def test_already_closed_session_does_not_log_a_pending_warning(self):
		sid = "closed-session"
		self.db.get_values.return_value = [
			SimpleNamespace(name=sessions._session_key(sid), delivery_pending=0),
		]
		sessions.revoke_after_commit([(sid, None)])
		self.logger.return_value.warning.assert_not_called()
		self.send.assert_not_called()

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
			patch.object(
				identity_sync_client, "_identity_sync_origin", return_value="https://sync.example.test"
			),
			patch.object(identity_sync_client, "identity_sync_bearer", return_value="fixture-bearer"),
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
