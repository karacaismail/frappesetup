"""Regressions for Keycloak session binding and revocation."""

import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase


class MobileSessionTest(IntegrationTestCase):
	def setUp(self):
		self.account = (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": f"mobile-sid-{uuid4().hex}@example.test",
					"first_name": "Mobile Session Test",
					"send_welcome_email": 0,
				}
			)
			.insert()
			.name
		)
		self.sid = str(uuid4())
		self.identity = SimpleNamespace(
			account=self.account,
			site=frappe.local.site,
			scope="mobile",
			principal="fixture",
			issued_at=int(time.time()),
			sid=self.sid,
			subject=str(uuid4()),
			installation=None,
			auth_time=int(time.time()),
		)
		self.body = {"installation_id": str(uuid4())}
		self.identity.installation = self.body["installation_id"]

	def test_registration_rebinds_one_installation_across_twenty_one_sessions(self):
		from platform_core.api.mobile import _register
		from platform_core.mobil.sessions import is_session_revoked

		previous = None
		for _ in range(21):
			current = str(uuid4())
			identity = SimpleNamespace(**{**vars(self.identity), "sid": current})
			_register(identity, self.body)
			if previous:
				self.assertTrue(is_session_revoked(previous))
			previous = current
		self.assertEqual(frappe.db.count("Mobile Installation", {"account": self.account, "revoked": 0}), 1)
		self.assertEqual(
			frappe.db.get_value("Mobile Installation", self.body["installation_id"], "session_id"), current
		)

	def test_http_delivery_is_enqueued_only_after_commit(self):
		from platform_core.mobil.sessions import revoke_after_commit

		queue = Mock()
		with (
			patch.object(frappe.local, "request", SimpleNamespace(after_response=queue), create=True),
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch("platform_core.mobil.sessions._deliver_committed") as deliver,
		):
			revoke_after_commit(((self.sid, self.identity.subject),))
			queue.add.assert_not_called()
			after_commit.add.call_args.args[0]()
			deliver.assert_not_called()
			queue.add.call_args.args[0]()
			deliver.assert_called_once_with(((self.sid, self.identity.subject),))

	def test_rebinding_sends_the_old_session_with_its_stored_subject(self):
		from platform_core.api.mobile import _register

		_register(self.identity, self.body)
		new_identity = SimpleNamespace(**{**vars(self.identity), "sid": str(uuid4())})
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch("platform_core.mobil.sessions._deliver_committed") as deliver,
		):
			_register(new_identity, self.body)
			for callback in after_commit.add.call_args_list:
				callback.args[0]()
			deliver.assert_called_once_with(((self.sid, self.identity.subject),))

	def test_legacy_installation_uses_only_a_matching_identity_link(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobil import ai_tools
		from platform_core.mobil.protocol import content_digest
		from platform_core.mobil.sessions import is_session_closure_pending

		issuer = "https://identity.example.test"
		subject = self.identity.subject
		self.identity.principal = content_digest([issuer, subject])
		self.identity.subject = None
		_register(self.identity, self.body)
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch("platform_core.mobil.store.identity_link", return_value=(issuer, "wrong-subject")) as link,
			patch("platform_core.mobil.sessions._deliver_committed") as deliver,
		):
			_revoke(self.identity, self.body)
			self.assertTrue(is_session_closure_pending(self.sid))
			for callback in after_commit.add.call_args_list:
				callback.args[0]()
			deliver.assert_not_called()
			after_commit.reset_mock()
			link.return_value = (issuer, subject)
			plan = ai_tools.prepare_revoke_installation(self.body["installation_id"])
			self.assertEqual(ai_tools.execute_revocation(plan)["revoked"], 0)
			for callback in after_commit.add.call_args_list:
				callback.args[0]()
			deliver.assert_called_once_with(((self.sid, subject),))

	def test_local_revocation_schedules_remote_close_only_after_commit(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobil.protocol import MobileError

		_register(self.identity, self.body)
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch("platform_core.mobil.sessions.send_session_revocations", return_value=()) as send,
			patch.object(frappe.db, "commit"),
		):
			after_commit.cut.return_value = []
			self.assertEqual(_revoke(self.identity, self.body), {"revoked": 1})
			with self.assertRaises(MobileError) as raised:
				_register(self.identity, {"installation_id": str(uuid4())})
			self.assertEqual(raised.exception.code, "mobile_session_revoked")
			send.assert_not_called()
			for call in list(after_commit.add.call_args_list):
				call.args[0]()
			send.assert_called_once_with(((self.sid, self.identity.subject),))
			from platform_core.mobil.sessions import is_session_closure_pending

			self.assertFalse(is_session_closure_pending(self.sid))

	def test_forbidden_remote_closure_stops_retry_and_keeps_installation_revoked(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobil import identity_sync_client
		from platform_core.mobil.sessions import is_session_closure_pending, is_session_revoked

		_register(self.identity, self.body)
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch.object(frappe.db, "commit"),
			patch.object(identity_sync_client, "_configured_url", return_value="https://sync.example.test"),
			patch.object(identity_sync_client, "_service_bearer", return_value="fixture-bearer"),
			patch.object(
				identity_sync_client._OPENER, "open", side_effect=HTTPError("", 403, "Forbidden", None, None)
			),
			patch.object(frappe, "logger") as logger,
		):
			after_commit.cut.return_value = []
			self.assertEqual(_revoke(self.identity, self.body), {"revoked": 1})
			self.assertTrue(is_session_closure_pending(self.sid))
			for callback in list(after_commit.add.call_args_list):
				callback.args[0]()
			self.assertFalse(is_session_closure_pending(self.sid))
			self.assertTrue(is_session_revoked(self.sid))
			self.assertTrue(
				frappe.db.get_value("Mobile Installation", self.body["installation_id"], "revoked")
			)
			logger.return_value.error.assert_called_once()

	def test_manager_can_retry_remote_closure_of_an_already_revoked_installation(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobil import ai_tools
		from platform_core.mobil.sessions import _session_key

		_register(self.identity, self.body)
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch(
				"platform_core.mobil.sessions.send_session_revocations",
				return_value=((self.sid, self.identity.subject),),
			) as send,
		):
			_revoke(self.identity, self.body)
			for call in list(after_commit.add.call_args_list):
				call.args[0]()
			send.assert_called_once_with(((self.sid, self.identity.subject),))
			after_commit.reset_mock()
			plan = ai_tools.prepare_revoke_installation(self.body["installation_id"])
			self.assertEqual(ai_tools.execute_revocation(plan)["revoked"], 0)
			after_commit.add.assert_not_called()
			frappe.db.set_value(
				"Mobile Revoked Session", _session_key(self.sid), "last_delivery_attempt_at", "1"
			)
			plan = ai_tools.prepare_revoke_installation(self.body["installation_id"])
			self.assertEqual(ai_tools.execute_revocation(plan)["revoked"], 0)
			for call in list(after_commit.add.call_args_list):
				call.args[0]()
			self.assertEqual(send.call_count, 2)

	def test_legacy_installation_gets_sid_on_explicit_registration(self):
		from platform_core.api.mobile import _register
		from platform_core.mobil.store import MobileStore

		legacy = SimpleNamespace(account=self.account, scope="mobile", principal="fixture")
		MobileStore().install(legacy, self.body["installation_id"])
		_register(self.identity, self.body)
		self.assertEqual(
			frappe.db.get_value("Mobile Installation", self.body["installation_id"], "session_id"), self.sid
		)

	def test_idle_boundary_checks_each_installation_and_background_does_not_renew_it(self):
		from platform_core.api.mobile import _activity, _pull, _push, _register
		from platform_core.mobil.protocol import MobileError

		_register(self.identity, self.body)
		table = "Mobile Installation"
		name = self.body["installation_id"]
		initial = int(time.time())
		with patch("platform_core.api.mobile.time.time", return_value=initial):
			_activity(self.identity, self.body)
		body = {**self.body, "operations": []}
		self.assertEqual(frappe.db.get_value("User", self.account, "user_type"), "Website User")
		for user_type in ("Website User", "System User"):
			if user_type != "Website User":
				frappe.db.set_value("User", self.account, "user_type", user_type)
			seconds = 3600
			with (
				patch("platform_core.api.mobile.time.time", return_value=initial + seconds - 1),
				patch("platform_core.api.mobile.push", return_value={}),
			):
				_push(self.identity, body)
			self.assertEqual(int(frappe.db.get_value(table, name, "last_user_activity_at")), initial)
			with patch("platform_core.api.mobile.time.time", return_value=initial + seconds):
				for action, payload in ((_push, body), (_pull, self.body), (_activity, self.body)):
					with self.assertRaises(MobileError) as raised:
						action(self.identity, payload)
					self.assertEqual(
						(raised.exception.status, raised.exception.code), (401, "reauthentication_required")
					)

	def test_same_sid_requires_new_authentication_time_to_unlock(self):
		from platform_core.api.mobile import _activity, _register
		from platform_core.mobil.protocol import MobileError

		started = self.identity.auth_time
		old_identity = SimpleNamespace(**vars(self.identity))
		_register(self.identity, self.body)
		with patch("platform_core.api.mobile.time.time", return_value=started + 3600):
			self.identity.issued_at = started + 3600
			_register(self.identity, self.body)
			with self.assertRaisesRegex(MobileError, "reauthentication_required"):
				_activity(self.identity, self.body)

			new_installation = {"installation_id": str(uuid4())}
			_register(self.identity, new_installation)
			with self.assertRaisesRegex(MobileError, "reauthentication_required"):
				_activity(self.identity, new_installation)

			self.identity.auth_time = started + 3600
			_register(self.identity, self.body)
			self.assertEqual(_activity(self.identity, self.body)["last_user_activity_at"], started + 3600)
			with self.assertRaisesRegex(MobileError, "reauthentication_required"):
				_activity(old_identity, self.body)

	def test_expired_phone_cannot_revoke_other_installations(self):
		from platform_core.api.mobile import _register, _revoke, _revoke_installation
		from platform_core.mobil.protocol import MobileError
		from platform_core.mobil.store import MobileStore

		self.identity.installation = self.body["installation_id"]
		_register(self.identity, self.body)
		other = {"installation_id": str(uuid4())}
		other_identity = SimpleNamespace(**{**vars(self.identity), "sid": str(uuid4())})
		_register(other_identity, other)
		with patch("platform_core.api.mobile.time.time", return_value=self.identity.auth_time + 3600):
			for action, payload in (
				(_revoke_installation, other),
				(_revoke, other),
				(_revoke, {"all": True}),
			):
				with self.assertRaisesRegex(MobileError, "reauthentication_required"):
					action(self.identity, payload)
		MobileStore().require_installation(other_identity, other["installation_id"])

	def test_device_revocation_clears_only_its_notification_binding(self):
		from platform_core.api.mobile import _register, _revoke

		other = {"installation_id": str(uuid4())}
		for body in (self.body, other):
			_register(self.identity, body)
			frappe.db.set_value(
				"Mobile Installation", body["installation_id"], "notification_token", "fixture"
			)
		_revoke(self.identity, self.body)
		self.assertIsNone(
			frappe.db.get_value("Mobile Installation", self.body["installation_id"], "notification_token")
		)
		self.assertEqual(
			frappe.db.get_value("Mobile Installation", other["installation_id"], "notification_token"),
			"fixture",
		)

	def test_cleanup_keeps_recent_session_denials(self):
		from datetime import timedelta

		from frappe.utils import now_datetime

		from platform_core.mobil.retention import cleanup
		from platform_core.mobil.sessions import _session_key, is_session_revoked, revoke_after_commit

		old = str(uuid4())
		revoke_after_commit(((old, None), (self.sid, None)), remote=False)
		frappe.db.set_value(
			"Mobile Revoked Session", _session_key(old), "creation", now_datetime() - timedelta(days=32)
		)
		self.assertEqual(cleanup(dry_run=True)["eligible_revoked_sessions"], 1)
		self.assertTrue(is_session_revoked(old))
		self.assertEqual(cleanup()["revoked_sessions_removed"], 1)
		self.assertFalse(is_session_revoked(old))
		self.assertTrue(is_session_revoked(self.sid))
