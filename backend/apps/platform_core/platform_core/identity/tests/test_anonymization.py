"""Tests of `platform_core.api.identity.anonymize_user` (PROJE-KAYDI.md O-27).

Expected behaviour comes from docs/sozlesmeler.md section 7, anonymization rules and the third
review decisions E1, E2, E3 and important finding 1 (D-1):
- only an `azp=identity-sync` service token may call it,
- step 1 disables the user, revokes API keys, records the deletion and closes every session page by page;
  step 2 anonymizes. Both steps are safe to repeat,
- the deletion record keeps only the HMAC-SHA256 digest of `(iss, sub)`; the raw `sub` is deleted,
- a deleted identity can never be provisioned, enabled or renamed again,
- only rows bound to the user change. Another person with the same full name keeps their text,
- business records stay; no e-mail goes to the user,
- the same request twice returns the same body; no link gives 404; Administrator gives 409.
"""

import base64
import hashlib
import hmac
import json
import threading
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.tests.test_api import FrappeAPITestCase

from platform_core.identity import anonymization, anonymization_scope, provider_setup
from platform_core.identity.tests import helpers as h

ANONYMIZE = "/api/method/platform_core.api.identity.anonymize_user"
PROVISION = "/api/method/platform_core.api.identity.provision"
SET_ENABLED = "/api/method/platform_core.api.identity.set_enabled"
CHANGE_EMAIL = "/api/method/platform_core.api.identity.change_email"
DELETED = "silinecek.musteri@example.test"
NAMESAKE = "adas.musteri@example.test"
SUBJECT = "sub-silinecek"
FULL_NAME = "Ayse Ornekoglu"
LINK = "PLT Identity Link"
DELETION = "Platform Identity Deletion"


def expected_hash() -> str:
	key = h.TEST_SETTINGS["kimlik_deletion_hmac_key"].encode()
	return hmac.new(key, f"{h.ISSUER}\n{SUBJECT}".encode(), hashlib.sha256).hexdigest()


class TestAnonymizeUser(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		cls.address_country = frappe.db.get_value("Country", {}, "name")
		if not (
			frappe.db.exists("Address Template", {"country": cls.address_country})
			or frappe.db.exists("Address Template", {"is_default": 1})
		):
			template = frappe.get_doc(
				{
					"doctype": "Address Template",
					"country": cls.address_country,
					"template": "{{ address_line1 }}",
				}
			).insert()
			cls.addClassCleanup(h.refresh)
			cls.addClassCleanup(frappe.db.delete, "Address Template", {"name": template.name})
		provider_setup.ensure_social_login_key()
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def setUp(self):
		super().setUp()
		h.clear_links(DELETED, NAMESAKE)
		self._remove_test_people()
		self.addCleanup(self._remove_test_people)
		h.ensure_user(DELETED)
		frappe.db.set_value("User", DELETED, {"first_name": "Ayse", "last_name": "Ornekoglu"})
		# Another person with the same full name (review finding E3).
		h.ensure_user(NAMESAKE)
		frappe.db.set_value("User", NAMESAKE, {"first_name": "Ayse", "last_name": "Ornekoglu"})
		for email in (DELETED, NAMESAKE):
			frappe.db.set_value("User", email, "full_name", FULL_NAME)
		self.link = h.make_link(SUBJECT, DELETED)
		# Frappe creates one Contact for a new website user (User.after_insert). The test uses that record.
		self.contact = frappe.db.get_value("Contact", {"email_id": DELETED}, "name")
		self.assertTrue(self.contact)
		frappe.db.set_value("Contact", self.contact, {"first_name": "Ayse", "last_name": "Ornekoglu"})
		# A business record owned by the person. It must stay after anonymization.
		self.todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "Ornek is kaydi", "allocated_to": DELETED}
		).insert(ignore_permissions=True)
		frappe.db.set_value("ToDo", self.todo.name, "owner", DELETED, update_modified=False)
		self.namesake_comment = self._comment(NAMESAKE, f"{FULL_NAME} yazdi")
		self.own_comment = self._comment(DELETED, f"Bana {DELETED} adresinden yazin")
		frappe.db.commit()

	def _comment(self, owner: str, content: str) -> frappe._dict:
		doc = frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "ToDo",
				"reference_name": self.todo.name,
				"content": content,
				"comment_email": owner,
				"comment_by": FULL_NAME,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Comment", doc.name, "owner", owner, update_modified=False)
		return doc

	@staticmethod
	def _remove_test_people():
		"""Removes the sample people and what earlier runs anonymized. Only test data is touched."""
		for email in (DELETED, NAMESAKE):
			for name in frappe.get_all("Contact Email", filters={"email_id": email}, pluck="parent"):
				frappe.delete_doc("Contact", name, force=True, ignore_permissions=True, ignore_missing=True)
		for name in frappe.get_all("Contact", filters={"name": ("like", "deleted-user-%")}, pluck="name"):
			frappe.delete_doc("Contact", name, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.delete("ToDo", {"description": "Ornek is kaydi"})
		frappe.db.delete("Comment", {"reference_doctype": "ToDo", "content": ("like", "%yaz%")})
		frappe.db.delete(DELETION, {"name": expected_hash()})
		frappe.db.delete(LINK, {"subject": SUBJECT})
		for name in frappe.get_all("User", filters={"name": ("like", "deleted-user-%")}, pluck="name"):
			frappe.delete_doc("User", name, force=True, ignore_permissions=True, ignore_missing=True)
		for email in (DELETED, NAMESAKE):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
		frappe.db.commit()

	def call(self, path=ANONYMIZE, body=None, **token):
		signed = self.key.sign(h.access_payload(**token))
		return h.request(
			h.new_client().post,
			path,
			json=body if body is not None else self.body(),
			headers={"Authorization": f"Bearer {signed}"},
		)

	def body(self, **overrides):
		data = {"issuer": h.ISSUER, "subject": SUBJECT}
		data.update(overrides)
		return data

	# --- result, record and anonymization ----------------------------------------------------------

	def test_user_is_disabled_renamed_and_anonymized(self):
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo(SUBJECT, DELETED))
		self.assertEqual(h.logged_user(client), DELETED)

		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:500])
		result = response.json["message"]
		self.assertEqual(set(result), {"user", "enabled", "status", "anonymized", "found"})
		self.assertRegex(result["user"], r"^deleted-user-[0-9a-f]{16}@deleted\.invalid$")
		self.assertIs(result["enabled"], False)
		self.assertEqual(result["status"], "Anonymized")
		self.assertIs(result["anonymized"], True)
		self.assertIs(result["found"], True)

		h.refresh()
		anon = result["user"]
		self.assertFalse(frappe.db.exists("User", DELETED))
		user = frappe.get_doc("User", anon)
		self.assertEqual(user.enabled, 0)
		for field in ("first_name", "last_name", "full_name", "email", "username"):
			value = (user.get(field) or "").lower()
			self.assertNotIn("ornekoglu", value, field)
			self.assertNotIn("silinecek", value, field)
		self.assertEqual(h.session_count(DELETED) + h.session_count(anon), 0)
		self.assertEqual(h.logged_user(client), "Guest")

	def test_deletion_record_keeps_only_the_digest_and_the_raw_sub_is_gone(self):
		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:500])
		h.refresh()
		record = frappe.db.get_value(
			DELETION, expected_hash(), ["identity_hash", "state", "user", "deleted_at"], as_dict=True
		)
		self.assertEqual(record.identity_hash, expected_hash())
		self.assertEqual(record.state, "Anonymized")
		self.assertEqual(record.user, response.json["message"]["user"])
		self.assertTrue(record.deleted_at)
		self.assertFalse(frappe.db.exists(LINK, {"subject": SUBJECT}))
		self.assertFalse(frappe.db.exists(LINK, self.link.name))
		for value in record.values():
			self.assertNotIn(SUBJECT, str(value))

	def test_only_rows_bound_to_the_user_change(self):
		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:500])
		h.refresh()
		self.assertFalse(frappe.db.exists("Contact Email", {"email_id": DELETED}))
		own = frappe.db.get_value(
			"Comment", self.own_comment.name, ["content", "comment_by", "comment_email"], as_dict=True
		)
		self.assertNotIn(DELETED, own.content)
		self.assertNotEqual(own.comment_email, DELETED)
		self.assertNotEqual(own.comment_by, FULL_NAME)
		# The namesake keeps everything (E3).
		other = frappe.db.get_value(
			"Comment", self.namesake_comment.name, ["content", "comment_by", "comment_email"], as_dict=True
		)
		self.assertEqual(other.content, f"{FULL_NAME} yazdi")
		self.assertEqual(other.comment_by, FULL_NAME)
		self.assertEqual(other.comment_email, NAMESAKE)
		self.assertEqual(frappe.db.get_value("User", NAMESAKE, "full_name"), FULL_NAME)
		self.assertTrue(frappe.db.get_value("User", NAMESAKE, "enabled"))
		# Business records stay.
		self.assertTrue(frappe.db.exists("ToDo", self.todo.name))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "description"), "Ornek is kaydi")
		self.assertNotEqual(frappe.db.get_value("ToDo", self.todo.name, "allocated_to"), DELETED)
		self.assertNotEqual(frappe.db.get_value("ToDo", self.todo.name, "owner"), DELETED)

	def test_shared_business_file_stays_and_personal_file_goes(self):
		# Merge review E3: a file bound to the User record is personal. A file on a business record is a
		# business record, even when the person uploaded it privately.
		personal = self._file("profil.txt", "User", DELETED)
		business = self._file("ortak-is.txt", "ToDo", self.todo.name)
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		self.assertFalse(frappe.db.exists("File", personal))
		self.assertTrue(frappe.db.exists("File", business))

	def test_personal_file_is_removed_from_disk_and_business_path_survives(self):
		business_doc = frappe.rename_doc("ToDo", self.todo.name, DELETED, force=True)
		self.addCleanup(frappe.delete_doc, "ToDo", business_doc, force=True, ignore_missing=True)
		personal = self._file("personal-audit.txt", "User", DELETED)
		business = self._file("business-audit.txt", "ToDo", business_doc)
		path = Path(frappe.get_doc("File", personal).get_full_path())
		url = frappe.db.get_value("File", business, "file_url")
		self.assertTrue(path.is_file())
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		self.assertFalse(path.exists())
		self.assertEqual(frappe.db.get_value("File", business, "file_url"), url)
		self.assertFalse(
			frappe.db.exists("Deleted Document", {"deleted_doctype": "File", "deleted_name": personal})
		)

	def _custom_todo_field(self, name: str, fieldtype: str, **properties):
		field = create_custom_field(
			"ToDo", {"fieldname": name, "label": name, "fieldtype": fieldtype, **properties}
		)
		self.addCleanup(frappe.delete_doc, "Custom Field", field.name, force=True, delete_permanently=True)

	def _with_todo_data_fields(self, **configuration):
		get_hooks = frappe.get_hooks

		def hooks(hook=None, *args, **kwargs):
			configured = get_hooks(hook, *args, **kwargs)
			if hook == "user_data_fields":
				return [*configured, {"doctype": "ToDo", **configuration}]
			return configured

		return patch.object(frappe, "get_hooks", side_effect=hooks)

	def test_clear_fields_clears_an_optional_unique_data_field(self):
		field = "custom_test_privacy_unique"
		self._custom_todo_field(field, "Data", unique=1)
		frappe.db.set_value("ToDo", self.todo.name, field, "TEST-ONLY-UNIQUE-DATA")
		frappe.db.commit()

		with self._with_todo_data_fields(redact_fields=[field], clear_fields=[field]):
			response = self.call()

		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.exists("ToDo", self.todo.name))
		self.assertIsNone(frappe.db.get_value("ToDo", self.todo.name, field))

	def test_clear_fields_rejects_a_required_field_without_changing_the_row(self):
		field = "description"
		original = frappe.db.get_value("ToDo", self.todo.name, field)
		self.addCleanup(frappe.db.delete, "ToDo", {"name": self.todo.name})

		with self._with_todo_data_fields(redact_fields=[field], clear_fields=[field]):
			response = self.call()

		self.assertEqual(response.status_code, 417, response.data[:300])
		self.assertEqual(response.json["exc_type"], "ValidationError")
		self.assertIn(b"clear_fields", response.data)
		self.assertIn(b"ToDo.description", response.data)
		h.refresh()
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, field), original)

	def test_redacted_attach_fields_delete_files_and_keep_unrelated_attachments(self):
		fields = {"custom_test_privacy_file": "Attach", "custom_test_privacy_image": "Attach Image"}
		personal = []
		for field, fieldtype in fields.items():
			self._custom_todo_field(field, fieldtype)
			file = self._file(f"{field}.txt", "ToDo", self.todo.name, field=field)
			doc = frappe.get_doc("File", file)
			path = Path(doc.get_full_path())
			self.assertTrue(path.is_file())
			frappe.db.set_value("ToDo", self.todo.name, field, doc.file_url)
			personal.append((file, path))
		unrelated = self._file("test-only-business-attachment.txt", "ToDo", self.todo.name)
		unrelated_path = Path(frappe.get_doc("File", unrelated).get_full_path())
		frappe.db.commit()

		with self._with_todo_data_fields(redact_fields=list(fields)):
			response = self.call()

		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		for field in fields:
			self.assertFalse(frappe.db.get_value("ToDo", self.todo.name, field))
		for file, path in personal:
			self.assertFalse(frappe.db.exists("File", file))
			self.assertFalse(path.exists())
			self.assertFalse(
				frappe.db.exists("Deleted Document", {"deleted_doctype": "File", "deleted_name": file})
			)
			self.assertFalse(
				frappe.db.exists(
					"Comment",
					{
						"reference_doctype": "ToDo",
						"reference_name": self.todo.name,
						"comment_type": ("in", ["Attachment", "Attachment Removed"]),
						"content": ("like", f"%{path.name}%"),
					},
				)
			)
		self.assertTrue(frappe.db.exists("File", unrelated))
		self.assertTrue(unrelated_path.is_file())

	def test_redacted_attach_field_keeps_file_and_thumbnail_shared_by_another_record(self):
		field = "custom_test_privacy_shared_file"
		self._custom_todo_field(field, "Attach")
		personal = self._file("test-only-shared-attachment.txt", "ToDo", self.todo.name, field=field)
		file = frappe.get_doc("File", personal)
		path = Path(file.get_full_path())
		another_todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "TEST-ONLY-SHARED-FILE-RECORD", "allocated_to": NAMESAKE}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.db.delete, "ToDo", {"name": another_todo.name})
		shared = file.create_attachment_copy("ToDo", another_todo.name, ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "File", shared.name, force=True, ignore_missing=True)
		self.assertEqual(shared.file_url, file.file_url)
		self.assertTrue(path.is_file())
		thumbnail_content = b"TEST-ONLY-SHARED-THUMBNAIL"
		thumbnail = path.with_name(f"thumbnail-{path.name}")
		thumbnail.write_bytes(thumbnail_content)
		self.addCleanup(thumbnail.unlink, missing_ok=True)
		thumbnail_url = f"/private/files/{thumbnail.name}"
		for name in (personal, shared.name):
			frappe.db.set_value("File", name, "thumbnail_url", thumbnail_url)
		frappe.db.set_value("ToDo", self.todo.name, field, file.file_url)
		frappe.db.commit()

		with self._with_todo_data_fields(redact_fields=[field]):
			response = self.call()

		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		self.assertFalse(frappe.db.exists("File", personal))
		self.assertTrue(frappe.db.exists("File", shared.name))
		self.assertTrue(path.is_file())
		self.assertEqual(frappe.db.get_value("File", shared.name, "thumbnail_url"), thumbnail_url)
		self.assertTrue(thumbnail.is_file(), "The surviving attachment still references the thumbnail")
		self.assertEqual(thumbnail.read_bytes(), thumbnail_content)

	def test_redacted_attach_field_keeps_thumbnail_used_by_a_different_file(self):
		field = "custom_test_privacy_thumbnail"
		self._custom_todo_field(field, "Attach Image")
		personal = self._file("test-only-personal-thumbnail.txt", "ToDo", self.todo.name, field=field)
		other = self._file("test-only-other-thumbnail.txt", "ToDo", self.todo.name)
		doc = frappe.get_doc("File", personal)
		path = Path(doc.get_full_path())
		thumbnail = path.with_name(f"thumbnail-{path.name}")
		thumbnail.write_bytes(b"TEST-ONLY-SHARED-THUMBNAIL")
		self.addCleanup(thumbnail.unlink, missing_ok=True)
		thumbnail_url = f"/private/files/{thumbnail.name}"
		self.assertNotEqual(doc.file_url, frappe.db.get_value("File", other, "file_url"))
		for name in (personal, other):
			frappe.db.set_value("File", name, "thumbnail_url", thumbnail_url)
		frappe.db.set_value("ToDo", self.todo.name, field, doc.file_url)
		frappe.db.commit()

		with self._with_todo_data_fields(redact_fields=[field]):
			response = self.call()

		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		self.assertFalse(path.exists())
		self.assertFalse(frappe.db.exists("File", personal))
		self.assertEqual(frappe.db.get_value("File", other, "thumbnail_url"), thumbnail_url)
		self.assertTrue(thumbnail.is_file(), "The other attachment uses this thumbnail")

	def test_history_scrubs_old_and_new_redacted_values_from_another_author(self):
		old = "TEST-ONLY-OLD-VALUE"
		new = "TEST-ONLY-NEW-VALUE"
		business_change = ["priority", "Low", "High"]
		changes = {"changed": [["description", old, new], business_change]}
		self.addCleanup(frappe.db.delete, "ToDo", {"name": self.todo.name})
		another_todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "TEST-ONLY-OTHER-RECORD", "allocated_to": NAMESAKE}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.db.delete, "ToDo", {"name": another_todo.name})
		versions = []
		for doc in (self.todo, another_todo):
			version = frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": "ToDo",
					"docname": doc.name,
					"data": json.dumps(changes),
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value("Version", version.name, "owner", "Administrator", update_modified=False)
			self.addCleanup(frappe.db.delete, "Version", {"name": version.name})
			versions.append(version.name)
		frappe.db.commit()

		with self._with_todo_data_fields(redact_fields=["description"]):
			response = self.call()

		self.assertEqual(response.status_code, 200, response.data[:300])
		h.refresh()
		target, unrelated = [frappe.db.get_value("Version", version, "data") for version in versions]
		self.assertNotIn(old, target)
		self.assertNotIn(new, target)
		self.assertIn(business_change, json.loads(target)["changed"])
		self.assertEqual(json.loads(unrelated), changes)

	def test_history_scrubs_version_committed_after_anonymization_snapshot(self):
		old = "TEST-ONLY-LATE-OLD-VALUE"
		new = "TEST-ONLY-LATE-NEW-VALUE"
		business_change = ["priority", "Low", "High"]
		changes = {"changed": [["description", old, new], business_change]}
		name = frappe.generate_hash(length=10)
		site = frappe.local.site
		todo = self.todo.name
		self.addCleanup(frappe.db.delete, "ToDo", {"name": todo})
		self.addCleanup(frappe.db.delete, "Version", {"name": name})
		result = {}

		def insert_version():
			frappe.init(site=site)
			try:
				frappe.connect()
				frappe.db.sql("SET SESSION innodb_lock_wait_timeout = 5")
				version = frappe.get_doc(
					{
						"doctype": "Version",
						"name": name,
						"ref_doctype": "ToDo",
						"docname": todo,
						"data": json.dumps(changes),
					}
				)
				version.set_user_and_timestamp()
				version.db_insert()
				frappe.db.commit()
				result["committed"] = True
			except Exception as error:
				result["error"] = error
			finally:
				frappe.destroy()

		def redact_after_snapshot(_issuer, _subject):
			if not result:
				frappe.db.sql("START TRANSACTION WITH CONSISTENT SNAPSHOT")
				self.assertIsNone(frappe.db.get_value("Version", name, "name"))
				worker = threading.Thread(target=insert_version)
				worker.start()
				worker.join(timeout=15)
				self.assertFalse(worker.is_alive(), "The Version writer did not finish")
				self.assertTrue(result.get("committed"), result)
				self.assertIsNone(frappe.db.get_value("Version", name, "name"))
			anonymization_scope._redact_version_fields("ToDo", todo, {"description"})

		anonymization._with_retry(redact_after_snapshot, h.ISSUER, SUBJECT)
		h.refresh()
		data = frappe.db.get_value("Version", name, "data")
		self.assertNotIn(old, data)
		self.assertNotIn(new, data)
		self.assertIn(business_change, json.loads(data)["changed"])

	def test_history_rejects_malformed_field_changes_without_overwriting_the_version(self):
		data = json.dumps(
			{"changed": {"description": "TEST-ONLY-MALFORMED"}, "added": [["tags", {"label": "Keep"}]]}
		)
		version = frappe.get_doc(
			{"doctype": "Version", "ref_doctype": "ToDo", "docname": self.todo.name, "data": data}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.db.delete, "Version", {"name": version.name})

		with self.assertRaisesRegex(frappe.ValidationError, "Version"):
			anonymization_scope._redact_version_fields("ToDo", self.todo.name, {"description"})

		self.assertEqual(frappe.db.get_value("Version", version.name, "data"), data)

	def test_communication_redacts_only_the_deleted_sender(self):
		body = "<p>Shared name and personal signature</p>"
		phone = "+90 000 000 00 01"
		names = {}
		for sender, recipient in ((DELETED, NAMESAKE), (NAMESAKE, DELETED)):
			message = frappe.get_doc(
				{
					"doctype": "Communication",
					"communication_type": "Communication",
					"sent_or_received": "Sent",
					"subject": "Sender privacy fixture",
					"sender": sender,
					"recipients": recipient,
					"sender_full_name": frappe.db.get_value("User", DELETED, "full_name"),
					"content": body,
					"phone_no": phone,
				}
			).insert()
			names[sender] = message.name
			self.addCleanup(frappe.delete_doc, "Communication", message.name, force=True)
		h.refresh()
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		fields = ["content", "phone_no"]
		with self.subTest(sender="namesake"):
			self.assertEqual(frappe.db.get_value("Communication", names[NAMESAKE], fields), (body, phone))
		with self.subTest(sender="deleted"):
			content, phone_no = frappe.db.get_value("Communication", names[DELETED], fields)
			self.assertEqual(content, "[REDACTED]")
			self.assertFalse(phone_no)

	def test_namesake_sender_and_direct_user_address(self):
		message = frappe.get_doc(
			{
				"doctype": "Communication",
				"subject": "Fixture",
				"sender": NAMESAKE,
				"sender_full_name": frappe.db.get_value("User", DELETED, "full_name"),
				"recipients": DELETED,
				"communication_type": "Communication",
				"sent_or_received": "Received",
			}
		).insert()
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Private fixture",
				"address_type": "Office",
				"address_line1": "Private street",
				"city": "Fixture city",
				"country": self.address_country,
				"links": [{"link_doctype": "User", "link_name": DELETED}],
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Communication", message.name, force=True)
		self.addCleanup(frappe.delete_doc, "Address", address.name, force=True)
		h.refresh()
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		self.assertEqual(
			frappe.db.get_value("Communication", message.name, "sender_full_name"), message.sender_full_name
		)
		self.assertNotEqual(frappe.db.get_value("Address", address.name, "address_line1"), "Private street")

	def test_only_the_exact_address_changes_in_e_mail_fields(self):
		similar = f"x.{DELETED}, {DELETED}.ornek"
		communication = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"subject": "Ornek konu",
				"sender": NAMESAKE,
				"recipients": f"{similar}, {DELETED}",
				"content": "Ornek ileti",
			}
		).insert(ignore_permissions=True)
		other = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"subject": "Benzer adres",
				"sender": NAMESAKE,
				"recipients": similar,
				"content": "Ornek ileti",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(frappe.db.delete, "Communication", {"name": ("in", [communication.name, other.name])})
		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:300])
		anon = response.json["message"]["user"]
		h.refresh()
		recipients = [
			a.strip()
			for a in frappe.db.get_value("Communication", communication.name, "recipients").split(",")
		]
		self.assertEqual(recipients, [f"x.{DELETED}", f"{DELETED}.ornek", anon])
		self.assertEqual(frappe.db.get_value("Communication", other.name, "recipients"), similar)

	def test_shared_contact_and_address_keep_the_other_persons_data(self):
		# Deletion rule: in shared records only the deleted person's own fields are anonymized.
		shared = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Ortak",
				"last_name": "Kayit",
				"email_ids": [
					{"email_id": DELETED, "is_primary": 1},
					{"email_id": NAMESAKE, "is_primary": 0},
				],
				"phone_nos": [{"phone": "+90 000 000 00 01", "is_primary_phone": 1}],
			}
		).insert(ignore_permissions=True)
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Ortak Is Adresi",
				"address_type": "Office",
				"address_line1": "Ornek Cadde 1",
				"city": "Ornekkent",
				"country": self.address_country,
				"email_id": DELETED,
				"links": [{"link_doctype": "Contact", "link_name": shared.name}],
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(
			frappe.delete_doc,
			"Address",
			address.name,
			force=True,
			ignore_permissions=True,
			ignore_missing=True,
		)
		self.addCleanup(
			frappe.delete_doc,
			"Contact",
			shared.name,
			force=True,
			ignore_permissions=True,
			ignore_missing=True,
		)
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		contact = frappe.get_doc("Contact", shared.name)
		self.assertEqual((contact.first_name, contact.last_name), ("Ortak", "Kayit"))
		self.assertEqual([row.email_id for row in contact.email_ids], [NAMESAKE])
		self.assertEqual([row.phone for row in contact.phone_nos], ["+90 000 000 00 01"])
		kept = frappe.db.get_value(
			"Address", address.name, ["address_title", "address_line1", "city", "email_id"], as_dict=True
		)
		self.assertEqual(
			(kept.address_title, kept.address_line1, kept.city),
			("Ortak Is Adresi", "Ornek Cadde 1", "Ornekkent"),
		)
		self.assertNotEqual(kept.email_id, DELETED)

	def test_address_with_an_apostrophe_is_another_persons_address(self):
		other = f"ekip'{DELETED}"
		communication = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"subject": "Kesme isareti",
				"sender": NAMESAKE,
				"recipients": f"{other}, {DELETED}",
				"cc": other,
				"content": f"Yaz: {other}",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Communication", communication.name, "owner", DELETED, update_modified=False)
		frappe.db.commit()
		self.addCleanup(frappe.db.delete, "Communication", {"name": communication.name})
		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:300])
		anon = response.json["message"]["user"]
		h.refresh()
		row = frappe.db.get_value(
			"Communication", communication.name, ["recipients", "cc", "content"], as_dict=True
		)
		self.assertEqual([a.strip() for a in row.recipients.split(",")], [other, anon])
		self.assertEqual(row.cc, other)
		self.assertIn(other, row.content)

	def test_contact_linked_to_a_business_record_is_shared(self):
		# Merge review 3: one e-mail does not prove the record is the person's. A Contact linked to a
		# business record is shared: only the person's e-mail goes, the company phone and file stay.
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Sirket",
				"last_name": "Iletisim",
				"email_ids": [{"email_id": DELETED, "is_primary": 1}],
				"phone_nos": [{"phone": "+90 000 000 00 02", "is_primary_phone": 1}],
				"links": [{"link_doctype": "ToDo", "link_name": self.todo.name}],
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(
			frappe.delete_doc,
			"Contact",
			contact.name,
			force=True,
			ignore_permissions=True,
			ignore_missing=True,
		)
		attached = self._file("sirket.txt", "Contact", contact.name)
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		kept = frappe.get_doc("Contact", contact.name)
		self.assertEqual((kept.first_name, kept.last_name), ("Sirket", "Iletisim"))
		self.assertEqual([row.phone for row in kept.phone_nos], ["+90 000 000 00 02"])
		self.assertEqual(kept.email_ids, [])
		self.assertNotEqual(kept.email_id, DELETED)
		self.assertTrue(frappe.db.exists("File", attached))

	def test_recipient_name_with_a_comma_is_one_recipient(self):
		other = f'"Diger,  Kisi"  <{NAMESAKE}>'
		recipients = f'"Ornekoglu, Ayse" <{DELETED}>, {other}'
		communication = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"subject": "Virgullu ad",
				"sender": NAMESAKE,
				"recipients": recipients,
				"content": "Ornek ileti",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Communication", communication.name, "recipients", recipients, update_modified=False
		)
		frappe.db.commit()
		self.addCleanup(frappe.db.delete, "Communication", {"name": communication.name})
		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:300])
		anon = response.json["message"]["user"]
		h.refresh()
		value = frappe.db.get_value("Communication", communication.name, "recipients")
		self.assertNotIn(DELETED, value)
		self.assertNotIn("Ornekoglu", value)
		self.assertIn(anon, value)
		self.assertTrue(value.endswith(other), value)

	def _file(self, name: str, doctype: str, docname: str, *, field: str | None = None) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": name,
				"content": name.encode(),
				"is_private": 1,
				"attached_to_doctype": doctype,
				"attached_to_name": docname,
				"attached_to_field": field,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("File", doc.name, "owner", DELETED, update_modified=False)
		frappe.db.commit()
		self.addCleanup(
			frappe.delete_doc, "File", doc.name, force=True, ignore_permissions=True, ignore_missing=True
		)
		return doc.name

	def test_no_mail_and_no_frappe_deletion_request(self):
		before = frappe.db.count("Personal Data Deletion Request")
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		self.assertEqual(frappe.db.count("Personal Data Deletion Request"), before)
		self.assertEqual(frappe.db.count("Email Queue Recipient", {"recipient": DELETED}), 0)

	def test_api_keys_are_revoked_even_if_the_account_comes_back(self):
		# Important finding 1: the key and its stored secret are deleted, not only refused for a disabled account.
		from frappe.utils.password import set_encrypted_password

		secret = frappe.generate_hash(length=15)
		frappe.db.set_value("User", DELETED, "api_key", "kimlikanahtar01")
		set_encrypted_password("User", DELETED, secret, "api_secret")
		frappe.db.commit()
		token = "token kimlikanahtar01:" + secret
		before = h.request(
			h.new_client().get, "/api/method/frappe.auth.get_logged_user", headers={"Authorization": token}
		)
		self.assertEqual(before.status_code, 200, before.data[:200])

		response = self.call()
		self.assertEqual(response.status_code, 200, response.data[:500])
		anon = response.json["message"]["user"]
		# A mistake re-enables the account. The old key must still fail.
		frappe.db.set_value("User", anon, "enabled", 1)
		frappe.db.commit()
		basic = "Basic " + base64.b64encode(f"kimlikanahtar01:{secret}".encode()).decode()
		for header in (token, basic):
			answer = h.request(
				h.new_client().get,
				"/api/method/frappe.auth.get_logged_user",
				headers={"Authorization": header},
			)
			self.assertIn(answer.status_code, (401, 403), answer.data[:200])
		self.assertFalse(frappe.db.get_value("User", anon, "api_key"))

	# --- E1: a deleted identity stays deleted ------------------------------------------------------

	def test_deleted_identity_cannot_be_provisioned_enabled_or_renamed(self):
		self.assertEqual(self.call().status_code, 200)
		provision = self.call(
			PROVISION,
			{
				"issuer": h.ISSUER,
				"subject": SUBJECT,
				"email": DELETED,
				"email_verified": True,
				"first_name": "Ayse",
				"last_name": "Ornekoglu",
				"enabled": True,
				"role_profiles": [],
			},
		)
		self.assertEqual(provision.status_code, 410, provision.data[:300])
		self.assertEqual(provision.json.get("exc_type"), "IdentityDeleted")
		enable = self.call(SET_ENABLED, {"issuer": h.ISSUER, "subject": SUBJECT, "enabled": True})
		self.assertEqual(enable.status_code, 410, enable.data[:300])
		rename = self.call(CHANGE_EMAIL, {"issuer": h.ISSUER, "subject": SUBJECT, "new_email": DELETED})
		self.assertEqual(rename.status_code, 410, rename.data[:300])
		h.refresh()
		self.assertFalse(frappe.db.exists("User", DELETED))
		self.assertFalse(frappe.db.exists(LINK, {"subject": SUBJECT}))

	def test_identity_closed_by_step_one_is_already_refused(self):
		with patch.object(anonymization, "anonymize_step", side_effect=RuntimeError("cut")):
			self.assertEqual(self.call().status_code, 500)
		h.refresh()
		self.assertEqual(frappe.db.get_value(DELETION, expected_hash(), "state"), "Disabled")
		enable = self.call(SET_ENABLED, {"issuer": h.ISSUER, "subject": SUBJECT, "enabled": True})
		self.assertEqual(enable.status_code, 410, enable.data[:300])
		self.assertEqual(frappe.db.get_value("User", DELETED, "enabled"), 0)

	def test_signed_in_after_deletion_is_refused(self):
		self.call()
		client = h.new_client()
		response = h.login_with_keycloak(client, h.userinfo(SUBJECT, DELETED))
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(h.logged_user(client), "Guest")

	# --- E2: two steps, repeatable, interrupted, concurrent ------------------------------------------

	def test_same_request_twice_returns_the_same_body(self):
		first = self.call()
		self.assertEqual(first.status_code, 200, first.data[:500])
		second = self.call()
		self.assertEqual(second.status_code, 200, second.data[:500])
		self.assertEqual(first.json["message"], second.json["message"])

	def test_interrupted_after_step_one_is_finished_by_the_retry(self):
		with patch.object(anonymization, "anonymize_step", side_effect=RuntimeError("cut")):
			cut = self.call()
		self.assertEqual(cut.status_code, 500, cut.data[:300])
		h.refresh()
		# Step 1 was committed: the account is closed and the deletion is recorded.
		self.assertEqual(frappe.db.get_value("User", DELETED, "enabled"), 0)
		self.assertEqual(frappe.db.get_value(DELETION, expected_hash(), "state"), "Disabled")
		self.assertTrue(frappe.db.exists(LINK, self.link.name))
		retry = self.call()
		self.assertEqual(retry.status_code, 200, retry.data[:500])
		self.assertEqual(retry.json["message"]["status"], "Anonymized")

	def test_failure_inside_step_two_leaves_no_half_anonymized_person(self):
		from platform_core.identity import anonymization_scope

		real = anonymization_scope._extra_records

		def broken(*args, **kwargs):
			real(*args, **kwargs)
			raise RuntimeError("cut inside step 2")

		with patch.object(anonymization_scope, "_extra_records", side_effect=broken):
			cut = self.call()
		self.assertEqual(cut.status_code, 500, cut.data[:300])
		h.refresh()
		self.assertEqual(frappe.db.get_value("User", DELETED, "first_name"), "Ayse")
		self.assertTrue(frappe.db.exists("Contact Email", {"email_id": DELETED}))
		self.assertEqual(frappe.db.get_value(DELETION, expected_hash(), "state"), "Disabled")
		self.assertEqual(self.call().status_code, 200)

	def test_many_sessions_are_closed_page_by_page(self):
		# Frappe returns at most 100 sessions per query (frappe/sessions.py:76).
		clients = [h.new_client() for _number in range(105)]
		for client in clients:
			h.login_with_keycloak(client, h.userinfo(SUBJECT, DELETED))
			h.reset_rate_limits()
		h.refresh()
		self.assertGreaterEqual(h.session_count(DELETED), 101)
		self.assertEqual(self.call().status_code, 200)
		h.refresh()
		self.assertEqual(h.session_count(DELETED), 0)

	def test_two_concurrent_calls_on_two_connections_finish_once(self):
		# Two database connections, as two workers would have (E2). Both calls return the same body.
		site = frappe.local.site
		results = {}
		start = threading.Barrier(2)

		def worker(name):
			frappe.init(site=site)
			frappe.connect()
			try:
				frappe.set_user("Administrator")
				start.wait(timeout=30)
				results[name] = anonymization.anonymize_user({"issuer": h.ISSUER, "subject": SUBJECT})
				frappe.db.commit()
			except Exception as error:
				results[name] = repr(error)
				frappe.db.rollback()
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b")]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=120)
		self.assertEqual(set(results), {"a", "b"})
		self.assertIsInstance(results["a"], dict, results)
		self.assertEqual(results["a"], results["b"])
		h.refresh()
		self.assertEqual(frappe.db.count("User", {"name": ("like", "deleted-user-%")}), 1)
		self.assertEqual(frappe.db.get_value(DELETION, expected_hash(), "state"), "Anonymized")

	# --- refusals ---------------------------------------------------------------------------------

	def test_unknown_identity_gets_404(self):
		response = self.call(body=self.body(subject="sub-yok"))
		self.assertEqual(response.status_code, 404, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "IdentityNotFound")
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", DELETED, "enabled"))

	def test_administrator_cannot_be_anonymized(self):
		frappe.db.set_value(LINK, self.link.name, "user", "Administrator")
		frappe.db.commit()
		response = self.call()
		self.assertEqual(response.status_code, 409, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "IdentityConflict")
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", "Administrator", "enabled"))
		self.assertFalse(frappe.db.exists(DELETION, expected_hash()))

	def test_missing_deletion_key_fails_closed(self):
		with h.SiteSettings({"kimlik_deletion_hmac_key": ""}):
			response = self.call()
			enable = self.call(SET_ENABLED, {"issuer": h.ISSUER, "subject": SUBJECT, "enabled": False})
		self.assertEqual(response.status_code, 503, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "DeletionKeyMissing")
		self.assertEqual(enable.status_code, 503, enable.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", DELETED, "enabled"))

	def test_missing_subject_gets_400(self):
		response = self.call(body={"issuer": h.ISSUER})
		self.assertEqual(response.status_code, 400, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")

	def test_other_service_client_is_refused(self):
		response = self.call(azp="press-service")
		self.assertIn(response.status_code, (401, 403), response.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.get_value("User", DELETED, "enabled"))

	def test_call_without_token_is_refused(self):
		response = h.request(h.new_client().post, ANONYMIZE, json=self.body())
		self.assertEqual(response.status_code, 403, response.data[:300])
		h.refresh()
		self.assertTrue(frappe.db.exists("User", DELETED))

	def test_desk_session_of_system_manager_is_refused(self):
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
