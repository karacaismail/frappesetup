"""Kayıt kuralı: çalışan yalnız kendi kaydını görür ve değiştirir (G-60)."""

import frappe

from platform_core.erisim.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	FREE_DOCTYPE,
	HR,
	NO_RULE,
	RULE_DOCTYPE,
	ErisimTestCase,
	employee_of,
)


class TestRecordRule(ErisimTestCase):
	def test_employee_lists_only_own_record(self):
		client = self.login(EMPLOYEE_1)

		self.assertEqual(self.listed_names(client), {self.records[EMPLOYEE_1]})

	def test_employee_reads_own_record(self):
		client = self.login(EMPLOYEE_1)

		response = self.rest_get(client, self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(response.json["data"]["employee"], employee_of(EMPLOYEE_1))

	def test_employee_cannot_read_another_employees_record(self):
		client = self.login(EMPLOYEE_1)

		response = self.rest_get(client, self.records[EMPLOYEE_2])

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_employee_cannot_write_another_employees_record(self):
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_2]

		response = self.rest_put(client, target, {"title": "Ele gecirildi"})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(self.stored(target, "title"), f"Talep {EMPLOYEE_2}")

	def test_employee_cannot_take_over_a_record_by_changing_its_employee(self):
		"""Karar notu 6. bölüm: saklı değer kurala uymuyorsa yeni değer işlemi kurtarmaz."""
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_2]

		response = self.rest_put(client, target, {"employee": employee_of(EMPLOYEE_1)})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(self.stored(target, "employee"), employee_of(EMPLOYEE_2))

	def test_employee_cannot_move_own_record_out_of_scope(self):
		"""G-60: kaydı kapsam dışına taşıyan güncelleme reddedilir."""
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_1]

		response = self.rest_put(client, target, {"employee": employee_of(EMPLOYEE_2)})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(self.stored(target, "employee"), employee_of(EMPLOYEE_1))

	def test_employee_updates_own_record(self):
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_1]
		self.addCleanup(frappe.db.set_value, DOCTYPE, target, "status", "Open")

		response = self.rest_put(client, target, {"status": "Closed"})

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(self.stored(target, "status"), "Closed")

	def test_employee_creates_only_for_self(self):
		client = self.login(EMPLOYEE_1)

		denied = self.rest_post(client, {"title": "Baskasi adina", "employee": employee_of(EMPLOYEE_2)})
		allowed = self.rest_post(client, {"title": "Kendi adima", "employee": employee_of(EMPLOYEE_1)})

		self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))
		self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True))
		self.addCleanup(frappe.delete_doc, DOCTYPE, allowed.json["data"]["name"], force=True)
		self.assertFalse(frappe.db.exists(DOCTYPE, {"title": "Baskasi adina"}))

	def test_employee_cannot_delete_own_record_without_delete_rule(self):
		"""Rol izni silmeyi açar ama çalışan kuralında `allow_delete` yoktur."""
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_1]

		response = self.rest_delete(client, target)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertTrue(frappe.db.exists(DOCTYPE, target))

	def test_role_without_rule_sees_nothing_on_governed_doctype(self):
		"""G-60: kurallı türde hiçbir kural uymazsa erişim yoktur."""
		client = self.login(NO_RULE)

		self.assertEqual(self.listed_names(client), set())
		self.assertEqual(self.rest_get(client, self.records[EMPLOYEE_1]).status_code, 403)

	def test_engine_leaves_ungoverned_doctype_to_role_permission(self):
		"""G-60: kuralı olmayan türde rol izni geçerlidir."""
		name = frappe.get_doc({"doctype": FREE_DOCTYPE, "title": "Serbest"}).insert().name
		self.addCleanup(frappe.delete_doc, FREE_DOCTYPE, name, force=True)
		client = self.login(NO_RULE)

		self.assertIn(name, self.listed_names(client, FREE_DOCTYPE))
		self.assertEqual(self.rest_get(client, name, FREE_DOCTYPE).status_code, 200)

	def test_all_scope_sees_every_record(self):
		client = self.login(HR)

		self.assertEqual(self.listed_names(client), set(self.records.values()))


class TestRuleFilters(ErisimTestCase):
	"""`filters` alanı kapsamı daraltır. Koşulların hepsi birden sağlanmalıdır."""

	RULES = (
		{
			"title": "Calisan acik kayitlari",
			"role": "ER Calisan",
			"scope": "own",
			"match_field": "employee",
			"filters": '[["status", "=", "Open"]]',
			"allow_read": 1,
		},
		{
			"title": "IK sirket kayitlari",
			"role": "ER IK",
			"scope": "all",
			"filters": '[["company", "=", "$user.company"]]',
			"allow_read": 1,
		},
	)

	def test_filter_narrows_scope_on_list_and_document(self):
		target = self.records[EMPLOYEE_1]
		frappe.db.set_value(DOCTYPE, target, "status", "Closed")
		self.addCleanup(frappe.db.set_value, DOCTYPE, target, "status", "Open")
		client = self.login(EMPLOYEE_1)

		self.assertEqual(self.listed_names(client), set())
		self.assertEqual(self.rest_get(client, target).status_code, 403)

	def test_user_variable_without_value_matches_nothing(self):
		"""İK kullanıcısının çalışan kaydı yoktur. `$user.company` boştur ve hiçbir kaydı seçmez."""
		client = self.login(HR)

		self.assertEqual(self.listed_names(client), set())


class TestRuleValidation(ErisimTestCase):
	"""Geçersiz kural kaydedilmez (karar notu 3. bölüm)."""

	def insert(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": RULE_DOCTYPE,
				"title": "Gecersiz",
				"document_type": DOCTYPE,
				"role": "ER Calisan",
				"scope": "own",
				"match_field": "employee",
				"allow_read": 1,
				**values,
			}
		)
		return doc.insert()

	def test_scope_requires_match_field(self):
		self.assertRaises(frappe.ValidationError, self.insert, match_field="")

	def test_match_field_must_exist(self):
		self.assertRaises(frappe.ValidationError, self.insert, match_field="no_such_field")

	def test_match_field_must_fit_scope(self):
		"""`own` kapsamı kullanıcı ya da çalışan ister. Şirket alanı uymaz."""
		self.assertRaises(frappe.ValidationError, self.insert, match_field="company")

	def test_filters_must_be_a_list_of_triples(self):
		self.assertRaises(frappe.ValidationError, self.insert, filters='{"status": "Open"}')

	def test_filter_operator_must_be_allowed(self):
		self.assertRaises(frappe.ValidationError, self.insert, filters='[["status", "like", "%"]]')

	def test_filter_field_must_be_a_column(self):
		self.assertRaises(frappe.ValidationError, self.insert, filters='[["1=1 or name", "=", "x"]]')

	def test_unknown_variable_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.insert, filters='[["title", "=", "$user.password"]]')

	def test_rule_on_permission_doctypes_is_rejected(self):
		for doctype in (RULE_DOCTYPE, "DocType", "Role", "Custom DocPerm", "User Permission"):
			self.assertRaises(
				frappe.ValidationError, self.insert, document_type=doctype, scope="all", match_field=""
			)

	def test_rule_on_child_table_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError, self.insert, document_type="Has Role", scope="all", match_field=""
		)
