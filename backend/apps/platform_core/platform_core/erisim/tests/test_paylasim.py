"""Paylaşım: paylaşılan kayıt kuralı aşar ve iki yüzeyde de görünür (G-12, karar notu 10. bölüm)."""

import frappe
import frappe.share

from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	EMPLOYEE_3,
	ErisimTestCase,
)

SHARE = "/api/method/frappe.share.add"


class TestSharing(ErisimTestCase):
	def share_with_employee_1(self, name: str, **rights) -> None:
		frappe.set_user("Administrator")
		frappe.share.add_docshare(DOCTYPE, name, EMPLOYEE_1, read=1, **rights)
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır
		self.addCleanup(self.unshare, name)

	def unshare(self, name: str) -> None:
		frappe.set_user("Administrator")
		frappe.db.delete("DocShare", {"share_doctype": DOCTYPE, "share_name": name})
		frappe.db.commit()  # nosemgrep

	def test_shared_record_is_visible_on_list_and_document(self):
		shared = self.records[EMPLOYEE_2]
		client = self.login(EMPLOYEE_1)
		self.assertEqual(self.rest_get(client, shared).status_code, 403)

		self.share_with_employee_1(shared)

		self.assertEqual(self.listed_names(client), {self.records[EMPLOYEE_1], shared})
		self.assertEqual(self.readable_names(client), {self.records[EMPLOYEE_1], shared})

	def test_read_share_does_not_allow_write(self):
		shared = self.records[EMPLOYEE_2]
		self.share_with_employee_1(shared)
		client = self.login(EMPLOYEE_1)

		response = self.rest_put(client, shared, {"title": "Paylasimla degisti"})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(self.stored(shared, "title"), f"Talep {EMPLOYEE_2}")

	def test_shared_record_cannot_be_deleted(self):
		"""Silme paylaşılamaz. Kural silmeyi kapsamadığı için ret sürer."""
		shared = self.records[EMPLOYEE_2]
		self.share_with_employee_1(shared, write=1)
		client = self.login(EMPLOYEE_1)

		response = self.rest_delete(client, shared)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertTrue(frappe.db.exists(DOCTYPE, shared))

	def test_user_outside_the_rule_cannot_share_a_record(self):
		"""`share` işlemi kayıt kancasından geçer. Çalışan göremediği kaydı paylaşamaz."""
		target = self.records[EMPLOYEE_3]
		client = self.login(EMPLOYEE_1)

		response = self.send(
			client, "POST", SHARE, body={"doctype": DOCTYPE, "name": target, "user": EMPLOYEE_2, "read": 1}
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": DOCTYPE, "share_name": target}))

	def test_explain_names_share_as_the_reason(self):
		shared = self.records[EMPLOYEE_2]
		self.share_with_employee_1(shared)
		admin = self.login(ADMIN)

		response = self.api(
			admin, "GET", "explain_permission", query={"doctype": DOCTYPE, "name": shared, "user": EMPLOYEE_1}
		)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		message = response.json["message"]
		self.assertTrue(message["allowed"])
		self.assertEqual(message["reason"], "allowed_by_share")
		self.assertEqual(message["layers"], {"role": True, "access_rule": False, "share": True})
