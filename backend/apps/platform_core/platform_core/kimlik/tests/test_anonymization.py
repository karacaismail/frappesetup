"""Tests of `platform_core.api.identity.anonymize_user` (PROJE-KAYDI.md O-27, docs/sozlesmeler.md section 5).

Expected behaviour comes from the contract `contracts/platform_core-kimlik.openapi.yaml` (D-1):
- only an `azp=identity-sync` service token may call it,
- the user is disabled, every session is closed and the user gets an anonymous name,
- fields that show the person are anonymized through the `user_data_fields` hooks,
- business records stay; no e-mail goes to the user,
- a “Personal Data Deletion Request” record ends as “Deleted” without the original e-mail,
- the same request twice returns the same body; no link gives 404; Administrator gives 409.
"""

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

ANONYMIZE = "/api/method/platform_core.api.identity.anonymize_user"
DELETED = "silinecek.musteri@example.test"
SUBJECT = "sub-silinecek"
REQUEST = "Personal Data Deletion Request"


class TestAnonymizeUser(FrappeAPITestCase):
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
		h.clear_links(DELETED)
		self._remove_test_people()
		self.addCleanup(self._remove_test_people)
		self.user = h.ensure_user(DELETED)
		frappe.db.set_value("User", DELETED, {"first_name": "Silinecek", "last_name": "Musteri"})
		self.link = h.make_link(SUBJECT, DELETED)
		# Frappe creates one Contact for a new website user (User.after_insert). The test uses that record.
		frappe.db.set_value(
			"Contact", {"email_id": DELETED}, {"first_name": "Silinecek", "last_name": "Musteri"}
		)
		self.contact = frappe.db.get_value("Contact", {"email_id": DELETED}, "name")
		self.assertTrue(self.contact)
		# A business record owned by the person. It must stay after anonymization.
		self.todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "Ornek is kaydi", "allocated_to": DELETED}
		).insert(ignore_permissions=True)
		frappe.db.set_value("ToDo", self.todo.name, "owner", DELETED, update_modified=False)
		frappe.db.commit()
		self.requests_before = frappe.db.count(REQUEST)

	@staticmethod
	def _remove_test_people():
		"""Removes the sample person and what earlier runs anonymized. Only test data is touched."""
		for name in frappe.get_all(
			"Contact Email", filters={"email_id": DELETED}, pluck="parent"
		) + frappe.get_all("Contact", filters={"name": ("like", "deleted-user-%")}, pluck="name"):
			frappe.delete_doc("Contact", name, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.delete("ToDo", {"description": "Ornek is kaydi"})
		for name in frappe.get_all("User", filters={"name": ("like", "deleted-user-%")}, pluck="name"):
			frappe.db.delete("Platform Identity Link", {"user": name})
			frappe.delete_doc("User", name, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("User", DELETED, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.commit()

	def call(self, body, **token):
		signed = self.key.sign(h.access_payload(**token))
		return h.request(
			h.new_client().post, ANONYMIZE, json=body, headers={"Authorization": f"Bearer {signed}"}
		)

	def body(self, **overrides):
		data = {"issuer": h.ISSUER, "subject": SUBJECT}
		data.update(overrides)
		return data

	def test_user_is_disabled_renamed_and_anonymized(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo(SUBJECT, DELETED))
		self.assertEqual(h.logged_user(client), DELETED)

		response = self.call(self.body())
		self.assertEqual(response.status_code, 200, response.data[:500])
		result = response.json["message"]
		self.assertEqual(set(result), {"user", "enabled", "status"})
		self.assertTrue(result["user"].startswith("deleted-user-"), result)
		self.assertNotIn("silinecek", result["user"])
		self.assertIs(result["enabled"], False)
		self.assertEqual(result["status"], "Deleted")

		h.refresh()
		anon = result["user"]
		self.assertFalse(frappe.db.exists("User", DELETED))
		user = frappe.get_doc("User", anon)
		self.assertEqual(user.enabled, 0)
		for field in ("first_name", "last_name", "full_name", "email"):
			self.assertNotIn("silinecek", (user.get(field) or "").lower(), field)
		# Sessions are closed. The old browser is a guest now.
		self.assertEqual(h.session_count(DELETED) + h.session_count(anon), 0)
		self.assertEqual(h.logged_user(client), "Guest")
		# The identity link follows the anonymous user and is kept for repeated requests.
		self.assertEqual(frappe.db.get_value("Platform Identity Link", self.link.name, "user"), anon)

	def test_person_fields_are_anonymized_and_business_records_stay(self):
		response = self.call(self.body())
		self.assertEqual(response.status_code, 200, response.data[:500])
		h.refresh()
		self.assertFalse(frappe.db.exists("Contact", self.contact))
		self.assertFalse(frappe.db.exists("Contact Email", {"email_id": DELETED}))
		contacts = frappe.get_all("Contact", filters={"name": response.json["message"]["user"]}, pluck="name")
		self.assertEqual(len(contacts), 1)
		for name in contacts:
			contact = frappe.get_doc("Contact", name)
			self.assertNotIn("silinecek", (contact.first_name or "").lower())
			self.assertNotIn(DELETED, [row.email_id for row in contact.email_ids])
		self.assertTrue(frappe.db.exists("ToDo", self.todo.name))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "description"), "Ornek is kaydi")
		self.assertNotEqual(frappe.db.get_value("ToDo", self.todo.name, "allocated_to"), DELETED)

	def test_deletion_request_record_has_no_original_email_and_no_mail_is_sent(self):
		response = self.call(self.body())
		self.assertEqual(response.status_code, 200, response.data[:500])
		h.refresh()
		self.assertEqual(frappe.db.count(REQUEST), self.requests_before + 1)
		anon = response.json["message"]["user"]
		record = frappe.get_doc(REQUEST, anon)
		self.assertEqual(record.status, "Deleted")
		self.assertNotEqual(record.email, DELETED)
		self.assertFalse(frappe.db.exists(REQUEST, {"email": DELETED}))
		self.assertEqual(frappe.db.count("Email Queue Recipient", {"recipient": DELETED}), 0)

	def test_same_request_twice_returns_the_same_body(self):
		first = self.call(self.body())
		self.assertEqual(first.status_code, 200, first.data[:500])
		second = self.call(self.body())
		self.assertEqual(second.status_code, 200, second.data[:500])
		self.assertEqual(first.json["message"], second.json["message"])
		h.refresh()
		self.assertEqual(frappe.db.count(REQUEST), self.requests_before + 1)

	def test_signed_in_after_anonymization_is_refused(self):
		self.call(self.body())
		client = h.new_client()
		response = h.login_with_keycloak(client, h.userinfo(SUBJECT, DELETED))
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(h.logged_user(client), "Guest")

	def test_link_and_request_are_read_with_row_locks(self):
		# Review finding: a retry that runs while the first call is still open must wait for it. Locking reads
		# (SELECT ... FOR UPDATE) serialize the two calls and see the committed anonymous name.
		from unittest.mock import patch

		from platform_core.kimlik import anonymization

		real = frappe.db.get_value
		calls = []

		def spy(doctype, *args, **kwargs):
			calls.append((doctype, kwargs.get("for_update")))
			return real(doctype, *args, **kwargs)

		with patch.object(frappe.db, "get_value", side_effect=spy):
			anonymization.anonymize_user({"issuer": h.ISSUER, "subject": SUBJECT})
		frappe.db.rollback()
		self.assertIn(("Platform Identity Link", True), calls)
		self.assertIn(("Personal Data Deletion Request", True), calls)

	def test_unknown_identity_gets_404(self):
		response = self.call(self.body(subject="sub-yok"))
		self.assertEqual(response.status_code, 404, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "IdentityNotFound")
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", DELETED, "enabled"))

	def test_administrator_cannot_be_anonymized(self):
		frappe.db.set_value("Platform Identity Link", self.link.name, "user", "Administrator")
		frappe.db.commit()
		response = self.call(self.body())
		self.assertEqual(response.status_code, 409, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "IdentityConflict")
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", "Administrator", "enabled"))

	def test_missing_subject_gets_400(self):
		response = self.call({"issuer": h.ISSUER})
		self.assertEqual(response.status_code, 400, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")

	def test_other_service_client_is_refused(self):
		response = self.call(self.body(), azp="press-service")
		self.assertIn(response.status_code, (401, 403), response.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", DELETED, "enabled"))

	def test_call_without_token_is_refused(self):
		response = h.request(h.new_client().post, ANONYMIZE, json=self.body())
		self.assertEqual(response.status_code, 403, response.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.exists("User", DELETED))

	def test_desk_session_of_system_manager_is_refused(self):
		# Only the service token may call the endpoint, not a person with a session (contract, security).
		client = h.new_client()
		password = frappe.generate_hash(length=24)
		h.ensure_system_manager("kimlik.yonetici@example.test", password)
		h.refresh()
		login = h.request(
			client.post, "/api/method/login", json={"usr": "kimlik.yonetici@example.test", "pwd": password}
		)
		self.assertEqual(login.status_code, 200, login.data[:200])
		response = h.request(client.post, ANONYMIZE, json=self.body(), headers=h.csrf_headers(client))
		self.assertIn(response.status_code, (401, 403), response.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.exists("User", DELETED))
