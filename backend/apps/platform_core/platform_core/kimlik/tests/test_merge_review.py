"""Regression tests for the pre-merge review (status file, 22 November 2026).

Expected behaviour comes from the orchestrator's decisions on the review findings (D-1):
- E1: sign-in and deletion use the same identity lock. Sign-in keeps it until the session row exists
  and reads the account state again under the lock. Tested with two database connections.
- E2: identity endpoints write only safe fields to the Error Log and the app log. `subject`, `email`,
  `new_email` and the token never appear there, nor in the response. Tested for 500 and 503.
- Ö1: a cookie session is checked for idle time even when the request carries an Authorization header.
- Ö2: a background method does not renew the idle time in any address form Frappe accepts.
- Ö3: the back-channel logout fallback finds old sessions on every page, not only on the first one.
"""

import glob
import json
import os
import threading
import time
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import anonymization, provider_setup, session_policy, sign_in
from platform_core.kimlik.tests import helpers as h

FAKE_SUBJECT = "sub-gizli-ornek-4711"
FAKE_EMAIL = "gizli.ornek.4711@example.test"
LINK = "Platform Identity Link"
DELETION = "Platform Identity Deletion"


_REAL_LOCK = anonymization.lock_identity


def _after_sign_in_lock(hook):
	"""Wraps the real identity lock. Runs `hook` once, right after the sign-in took its first lock (D-4)."""
	state = {"done": False}

	def wrapper(*args, **kwargs):
		result = _REAL_LOCK(*args, **kwargs)
		if kwargs.get("require_key") is False and not state["done"]:
			state["done"] = True
			hook()
		return result

	return wrapper


def _deletion_worker(site: str, results: dict, done: threading.Event):
	frappe.init(site=site)
	frappe.connect()
	try:
		frappe.set_user("Administrator")
		results["deletion"] = anonymization.anonymize_user({"issuer": h.ISSUER, "subject": FAKE_SUBJECT})
		frappe.db.commit()
	except Exception as error:
		results["deletion"] = repr(error)
		frappe.db.rollback()
	finally:
		done.set()
		frappe.destroy()


class TestMergeReview(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def setUp(self):
		super().setUp()
		self._cleanup()
		self.addCleanup(self._cleanup)
		h.ensure_user(FAKE_EMAIL)
		self.link = h.make_link(FAKE_SUBJECT, FAKE_EMAIL)
		frappe.cache.delete_keys(session_policy.ACTIVITY_PREFIX)
		h.reset_rate_limits()
		frappe.db.commit()

	@staticmethod
	def _cleanup():
		h.clear_sessions_of(FAKE_EMAIL)
		frappe.db.delete(LINK, {"subject": FAKE_SUBJECT})
		frappe.db.delete(DELETION, {"name": anonymization.identity_hash(h.ISSUER, FAKE_SUBJECT)})
		for name in frappe.get_all("User", filters={"name": ("like", "deleted-user-%")}, pluck="name"):
			frappe.delete_doc("User", name, force=True, ignore_permissions=True, ignore_missing=True)
		for name in frappe.get_all("Contact Email", filters={"email_id": FAKE_EMAIL}, pluck="parent"):
			frappe.delete_doc("Contact", name, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("User", FAKE_EMAIL, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.commit()

	def service(self, name, body):
		signed = self.key.sign(h.access_payload())
		return (
			h.request(
				h.new_client().post,
				f"/api/method/platform_core.api.identity.{name}",
				json=body,
				headers={"Authorization": f"Bearer {signed}"},
			),
			signed,
		)

	# --- E1 -----------------------------------------------------------------------------------------

	def test_deletion_waits_for_a_sign_in_that_holds_the_lock_and_then_closes_its_session(self):
		site = frappe.local.site
		results, done = {}, threading.Event()
		observed = {}

		def while_locked():
			thread = threading.Thread(target=_deletion_worker, args=(site, results, done))
			thread.start()
			observed["finished_while_locked"] = done.wait(timeout=3)
			observed["thread"] = thread

		client = h.new_client()
		with patch.object(anonymization, "lock_identity", side_effect=_after_sign_in_lock(while_locked)):
			response = h.login_with_keycloak(client, h.userinfo(FAKE_SUBJECT, FAKE_EMAIL))
		observed["thread"].join(timeout=120)
		# Either order ends without a live session: the sign-in wins and the deletion closes its session,
		# or the deletion commits step 1 first and the sign-in refuses with 403.
		self.assertIn(response.status_code, (302, 403), f"{observed} {results} {response.data[-300:]}")
		self.assertFalse(observed["finished_while_locked"], "deletion did not wait for the sign-in lock")
		self.assertIsInstance(results.get("deletion"), dict, results)
		h.refresh()
		anon = results["deletion"]["user"]
		self.assertEqual(h.session_count(FAKE_EMAIL) + h.session_count(anon), 0)
		self.assertEqual(h.logged_user(client), "Guest")

	def test_sign_in_after_step_one_is_refused_under_the_lock(self):
		anonymization.disable_step(h.ISSUER, FAKE_SUBJECT)
		frappe.db.commit()
		client = h.new_client()
		response = h.login_with_keycloak(client, h.userinfo(FAKE_SUBJECT, FAKE_EMAIL))
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(h.logged_user(client), "Guest")
		self.assertEqual(h.session_count(FAKE_EMAIL), 0)

	def test_sign_in_reads_the_account_state_again_under_the_lock(self):
		def disable_meanwhile():
			frappe.db.set_value("User", FAKE_EMAIL, "enabled", 0)

		client = h.new_client()
		with patch.object(anonymization, "lock_identity", side_effect=_after_sign_in_lock(disable_meanwhile)):
			response = h.login_with_keycloak(client, h.userinfo(FAKE_SUBJECT, FAKE_EMAIL))
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(h.logged_user(client), "Guest")

	# --- E2 -----------------------------------------------------------------------------------------

	def _assert_no_personal_data(self, response, token, since):
		body = response.data.decode()
		for secret in (FAKE_SUBJECT, FAKE_EMAIL, token):
			self.assertNotIn(secret, body)
		h.refresh()
		logs = frappe.get_all(
			"Error Log", filters={"creation": (">=", since)}, fields=["method", "error", "trace_id"]
		)
		self.assertTrue(logs, "a safe Error Log entry is written")
		for row in logs:
			text = json.dumps(row, default=str)
			for secret in (FAKE_SUBJECT, FAKE_EMAIL, token):
				self.assertNotIn(secret, text)
		for path, start in self.log_sizes.items():
			with open(path, encoding="utf-8", errors="ignore") as handle:
				handle.seek(start)
				written = handle.read()
			for secret in (FAKE_SUBJECT, FAKE_EMAIL, token):
				self.assertNotIn(secret, written, path)

	def _remember_log_sizes(self):
		paths = glob.glob(os.path.join(frappe.get_site_path("logs"), "*.log")) + glob.glob(
			os.path.join(frappe.utils.get_bench_path(), "logs", "*.log")
		)
		self.log_sizes = {path: os.path.getsize(path) for path in paths}

	def test_unexpected_error_logs_only_safe_fields(self):
		since = frappe.utils.now()
		self._remember_log_sizes()
		time.sleep(1)
		boom = RuntimeError(f"failure for {FAKE_SUBJECT} and {FAKE_EMAIL}")
		with patch("platform_core.kimlik.provisioning.change_email", side_effect=boom):
			response, token = self.service(
				"change_email", {"issuer": h.ISSUER, "subject": FAKE_SUBJECT, "new_email": FAKE_EMAIL}
			)
		self.assertEqual(response.status_code, 500, response.data[:300])
		self._assert_no_personal_data(response, token, since)

	def test_missing_deletion_key_logs_only_safe_fields(self):
		since = frappe.utils.now()
		self._remember_log_sizes()
		time.sleep(1)
		with h.SiteSettings({"kimlik_deletion_hmac_key": ""}):
			response, token = self.service("anonymize_user", {"issuer": h.ISSUER, "subject": FAKE_SUBJECT})
		self.assertEqual(response.status_code, 503, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "DeletionKeyMissing")
		self._assert_no_personal_data(response, token, since)

	# --- Ö1 -----------------------------------------------------------------------------------------

	def test_idle_cookie_session_ends_even_with_an_authorization_header(self):
		for header in ("token abc:def", "Bearer not-a-token", "Basic YWJjOmRlZg=="):
			client = h.new_client()
			h.login_with_keycloak(client, h.userinfo(FAKE_SUBJECT, FAKE_EMAIL))
			frappe.cache.delete_value(session_policy._session_key(client.get_cookie("sid").value))
			answer = h.request(
				client.get,
				"/api/method/frappe.client.get_count",
				query_string={"doctype": "ToDo"},
				headers={"Authorization": header},
			)
			self.assertIn(answer.status_code, (401, 403), f"{header}: {answer.data[:200]}")
			self.assertEqual(h.logged_user(client), "Guest", header)
			h.reset_rate_limits()

	# --- Ö2 -----------------------------------------------------------------------------------------

	def test_background_method_does_not_renew_in_any_address_form(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo(FAKE_SUBJECT, FAKE_EMAIL))
		key = session_policy._session_key(client.get_cookie("sid").value)
		frappe.cache.set_value(key, 123, expires_in_sec=3600)
		method = "frappe.auth.get_logged_user"
		for call in (
			lambda: h.request(client.get, f"/api/method/{method}"),
			lambda: h.request(client.get, f"/api/v1/method/{method}"),
			lambda: h.request(client.get, f"/api/v2/method/{method}"),
			lambda: h.request(client.post, "/", data={"cmd": method}, headers=h.csrf_headers(client)),
			lambda: h.request(client.get, "/", query_string={"cmd": method}),
			lambda: h.request(client.post, "/", json={"cmd": method}, headers=h.csrf_headers(client)),
		):
			# Merge review 3: the request must really run. A refused request would not renew the time either.
			answer = call()
			self.assertEqual(answer.status_code, 200, answer.data[:200])
			self.assertEqual(answer.json.get("message", answer.json.get("data")), FAKE_EMAIL)
			self.assertEqual(frappe.cache.get_value(key, expires=True, use_local_cache=False), 123)

	# --- Ö3 -----------------------------------------------------------------------------------------

	def test_sub_fallback_finds_old_sessions_after_a_full_page_of_new_ones(self):
		now = frappe.utils.now_datetime()
		iat = int(time.time()) - 600
		old = [self._fake_session(now, minutes_ago=30, lastupdate_minutes_ago=1) for _n in range(3)]
		for _n in range(105):
			self._fake_session(now, minutes_ago=1, lastupdate_minutes_ago=20)
		frappe.db.commit()
		token = self.key.sign(
			h.logout_payload(sub=FAKE_SUBJECT, sid="77777777-7777-4777-8777-777777777777", iat=iat)
		)
		client = h.new_client()
		response = h.request(
			client.post,
			"/api/method/platform_core.api.keycloak_backchannel_logout",
			data={"logout_token": token},
			content_type="application/x-www-form-urlencoded",
			headers=h.csrf_headers(client),
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"closed_sessions": 3})
		h.refresh()
		for sid in old:
			self.assertFalse(frappe.db.exists("Sessions", {"sid": sid}))
		self.assertEqual(h.session_count(FAKE_EMAIL), 105)

	def test_sub_fallback_has_no_page_limit(self):
		# Merge review 2, Ö3: the search goes to the last page. The page size and the old cap are made small
		# so that the old session sits after the old cap.
		from platform_core.kimlik import sign_out

		now = frappe.utils.now_datetime()
		iat = int(time.time()) - 600
		for _n in range(6):
			self._fake_session(now, minutes_ago=1, lastupdate_minutes_ago=20)
		old = self._fake_session(now, minutes_ago=30, lastupdate_minutes_ago=1)
		frappe.db.commit()
		token = self.key.sign(
			h.logout_payload(sub=FAKE_SUBJECT, sid="88888888-8888-4888-8888-888888888888", iat=iat)
		)
		client = h.new_client()
		with patch.object(sign_out, "BATCH", 2), patch.object(sign_out, "MAX_BATCHES", 2, create=True):
			response = h.request(
				client.post,
				"/api/method/platform_core.api.keycloak_backchannel_logout",
				data={"logout_token": token},
				content_type="application/x-www-form-urlencoded",
				headers=h.csrf_headers(client),
			)
		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"closed_sessions": 1})
		h.refresh()
		self.assertFalse(frappe.db.exists("Sessions", {"sid": old}))

	def test_unexpected_callback_error_logs_only_safe_fields(self):
		since = frappe.utils.now()
		self._remember_log_sizes()
		time.sleep(1)
		code, state = "kod-gizli-ornek-4711", "durum-gizli-ornek-4711"
		boom = RuntimeError(f"failure for {code} {state} {FAKE_EMAIL}")
		with patch.object(sign_in, "complete_callback", side_effect=boom):
			response = h.request(h.new_client().get, h.CALLBACK, query_string={"code": code, "state": state})
		self.assertEqual(response.status_code, 500, response.data[:300])
		for secret in (code, state):
			self.assertNotIn(secret, response.data.decode())
		self._assert_no_personal_data(response, code, since)
		self._assert_no_personal_data(response, state, since)

	def test_unexpected_back_channel_error_logs_only_safe_fields(self):
		from platform_core.kimlik import sign_out

		since = frappe.utils.now()
		self._remember_log_sizes()
		time.sleep(1)
		token = "belirtec-gizli-ornek-4711"
		boom = RuntimeError(f"failure for {token} {FAKE_SUBJECT}")
		with patch.object(sign_out, "handle_logout_token", side_effect=boom):
			client = h.new_client()
			response = h.request(
				client.post,
				"/api/method/platform_core.api.keycloak_backchannel_logout",
				data={"logout_token": token},
				content_type="application/x-www-form-urlencoded",
				headers=h.csrf_headers(client),
			)
		self.assertEqual(response.status_code, 500, response.data[:300])
		self._assert_no_personal_data(response, token, since)

	@staticmethod
	def _fake_session(now, minutes_ago: int, lastupdate_minutes_ago: int) -> str:
		sid = frappe.generate_hash()
		created = frappe.utils.add_to_date(now, minutes=-minutes_ago, as_string=True, as_datetime=True)
		updated = frappe.utils.add_to_date(
			now, minutes=-lastupdate_minutes_ago, as_string=True, as_datetime=True
		)
		sessions = frappe.qb.DocType("Sessions")
		frappe.qb.into(sessions).columns(
			sessions.sid, sessions.user, sessions.sessiondata, sessions.lastupdate, sessions.status
		).insert(
			sid, FAKE_EMAIL, json.dumps({"creation": created, "user": FAKE_EMAIL}), updated, "Active"
		).run()
		return sid
