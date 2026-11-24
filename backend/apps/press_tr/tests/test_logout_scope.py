"""Press sessions after "sign out this device" and "sign out all devices" (G-163, sentences 7 and 12).

The Keycloak account console closes one session or every session of the user. Keycloak then sends
one back-channel logout token for each closed session. The token carries the session's `sid`.
These tests feed such tokens to Press and look at the Press sessions that remain.
Keycloak and the database are replaced by small in-memory fakes.
"""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from press_tr import api

ISSUER = "https://identity.example.test/realms/platform"
AYSE_LINK = "link-ayse"
MEHMET_LINK = "link-mehmet"


class FakeSite:
	"""Keycloak session mappings and Frappe sessions of a Press site."""

	def __init__(self):
		# mapping name -> (Keycloak sid, identity link, Press session id)
		self.mappings = {}
		# Press session id -> user
		self.sessions = {}

	def sign_in(self, mapping, keycloak_sid, link, press_sid, user):
		self.mappings[mapping] = (keycloak_sid, link, press_sid)
		self.sessions[press_sid] = user

	def pages(self, filters):
		names = sorted(
			name
			for name, (keycloak_sid, link, _press_sid) in self.mappings.items()
			if filters.get("keycloak_sid", keycloak_sid) == keycloak_sid
			and filters.get("identity_link", link) == link
		)
		if names:
			yield names

	def press_sid(self, mapping):
		return self.mappings[mapping][2]

	def delete_session(self, sid, user, reason):
		if self.sessions.pop(sid) != user:
			raise AssertionError(f"session {sid} belongs to another user")

	def delete_mapping(self, doctype, name, ignore_permissions):
		del self.mappings[name]

	def users_for(self, press_sids):
		return [(sid, self.sessions[sid]) for sid in press_sids if sid in self.sessions]


class LogoutScopeTest(unittest.TestCase):
	def setUp(self):
		self.site = FakeSite()
		self.site.sign_in("m-1", "sid-phone", AYSE_LINK, "press-phone-1", "ayse@example.test")
		self.site.sign_in("m-2", "sid-phone", AYSE_LINK, "press-phone-2", "ayse@example.test")
		self.site.sign_in("m-3", "sid-laptop", AYSE_LINK, "press-laptop", "ayse@example.test")
		self.site.sign_in("m-4", "sid-mehmet", MEHMET_LINK, "press-mehmet", "mehmet@example.test")
		stack = ExitStack()
		self.addCleanup(stack.close)
		framework = stack.enter_context(patch.object(api, "frappe"))
		framework.delete_doc.side_effect = self.site.delete_mapping
		selected = {}
		sessions = MagicMock()
		sessions.sid.isin.side_effect = lambda sids: selected.update(sids=list(sids))
		framework.qb.DocType.return_value = sessions
		framework.qb.from_.return_value.select.return_value.where.return_value.run.side_effect = lambda: (
			self.site.users_for(selected["sids"])
		)
		stack.enter_context(patch.object(api, "session_mapping_pages", side_effect=self.site.pages))
		stack.enter_context(patch.object(api, "read_press_session_id", side_effect=self.site.press_sid))
		stack.enter_context(patch.object(api, "delete_session", side_effect=self.site.delete_session))
		stack.enter_context(patch.object(api, "verify", side_effect=self.claims))
		stack.enter_context(patch.object(api, "client_id", return_value="press"))
		stack.enter_context(
			patch.object(
				api, "find_identity", side_effect=lambda issuer, subject: SimpleNamespace(name=subject)
			)
		)
		stack.enter_context(
			patch.dict("sys.modules", {"oidc_verify": SimpleNamespace(verify_logout_token=None)})
		)

	@staticmethod
	def claims(_verify, token, client_id):
		# Signature checks are faked. The token text names the subject and the session.
		subject, sid = token.split(" ")
		return {"iss": ISSUER, "sub": subject, "sid": sid}

	def logout(self, sid, link=AYSE_LINK):
		api._revoke_keycloak_sessions(f"{link} {sid}")

	def test_forgetting_one_device_closes_its_sessions_and_spares_the_other_device(self):
		self.logout("sid-phone")
		self.assertEqual(
			self.site.sessions, {"press-laptop": "ayse@example.test", "press-mehmet": "mehmet@example.test"}
		)
		self.assertEqual(sorted(self.site.mappings), ["m-3", "m-4"])

	def test_signing_out_every_device_closes_every_press_session_of_the_user(self):
		for sid in ("sid-phone", "sid-laptop"):
			self.logout(sid)
		self.assertEqual(self.site.sessions, {"press-mehmet": "mehmet@example.test"})
		self.assertEqual(sorted(self.site.mappings), ["m-4"])

	def test_a_token_cannot_close_another_users_session_with_a_borrowed_sid(self):
		self.logout("sid-mehmet")
		self.assertIn("press-mehmet", self.site.sessions)
		self.assertEqual(len(self.site.sessions), 4)


if __name__ == "__main__":
	unittest.main()
