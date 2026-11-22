"""The cases the independent review found (R-9). Each test checks one finding."""

import json

import frappe

from platform_core.access.tests.base import (
	ADMIN,
	COMPANY,
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	EMPLOYEE_3,
	HR,
	MANAGER_1,
	ROLE_EMPLOYEE,
	RULE_DOCTYPE,
	AccessRuleTestCase,
	employee_of,
)

SET_VALUE = "/api/method/frappe.client.set_value"
BULK_UPDATE = "/api/method/frappe.client.bulk_update"
PREPARED = "/api/method/frappe.core.doctype.prepared_report.prepared_report.make_prepared_report"
QUERY_REPORT = "ER Test Sorgu Raporu"


class TestIdentitySwap(AccessRuleTestCase):
	"""Finding 1: the client cannot reach the record of someone else by changing the name of the record."""

	def swap_fields(self) -> dict:
		own = self.records[EMPLOYEE_1]
		return {
			"name": own,
			"modified": str(frappe.db.get_value(DOCTYPE, own, "modified")),
			"employee": employee_of(EMPLOYEE_1),
		}

	def assert_untouched(self, response) -> None:
		own, victim = self.records[EMPLOYEE_1], self.records[EMPLOYEE_2]
		self.assertFalse(
			f"Talep {EMPLOYEE_2}" in response.get_data(as_text=True),
			"the response carries a value it must not carry",
		)
		self.assertGreaterEqual(response.status_code, 400)
		self.assertEqual(self.stored(own, "title"), f"Talep {EMPLOYEE_1}")
		self.assertEqual(self.stored(victim, "title"), f"Talep {EMPLOYEE_2}")
		self.assertEqual(self.stored(victim, "employee"), employee_of(EMPLOYEE_2))

	def test_set_value_cannot_swap_the_record_name(self):
		response = self.send(
			self.login(EMPLOYEE_1),
			"POST",
			SET_VALUE,
			body={"doctype": DOCTYPE, "name": self.records[EMPLOYEE_2], "fieldname": self.swap_fields()},
		)

		self.assert_untouched(response)

	def test_bulk_update_cannot_swap_the_record_name(self):
		docs = [{"doctype": DOCTYPE, "docname": self.records[EMPLOYEE_2], **self.swap_fields()}]

		response = self.send(self.login(EMPLOYEE_1), "POST", BULK_UPDATE, body={"docs": json.dumps(docs)})

		self.assertFalse(
			f"Talep {EMPLOYEE_2}" in response.get_data(as_text=True),
			"the response carries a value it must not carry",
		)
		self.assertEqual(self.stored(self.records[EMPLOYEE_1], "title"), f"Talep {EMPLOYEE_1}")
		self.assertEqual(self.stored(self.records[EMPLOYEE_2], "employee"), employee_of(EMPLOYEE_2))

	def test_rest_update_cannot_swap_the_record_name(self):
		response = self.rest_put(self.login(EMPLOYEE_1), self.records[EMPLOYEE_2], self.swap_fields())

		self.assert_untouched(response)


class TestValueTypes(AccessRuleTestCase):
	"""Finding 4: a number, list or dict value cannot pass the rule."""

	def test_numeric_employee_value_cannot_create_a_record(self):
		"""MariaDB counts the comparison `0 = 'HR-EMP-1'` as true. The engine must turn the value into text."""
		client = self.login(EMPLOYEE_1)

		response = self.rest_post(client, {"title": "Sayi ile", "employee": 0})

		self.assertEqual(response.status_code, 403)
		self.assertFalse(frappe.db.exists(DOCTYPE, {"title": "Sayi ile"}))

	def test_numeric_employee_value_cannot_move_a_record_out_of_scope(self):
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_1]

		response = self.rest_put(client, target, {"employee": 0})

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.stored(target, "employee"), employee_of(EMPLOYEE_1))

	def test_list_or_dict_value_is_denied_without_a_server_error(self):
		client = self.login(EMPLOYEE_1)
		for value in (["x"], {"a": 1}):
			response = self.rest_post(client, {"title": "Liste ile", "employee": value})

			self.assertIn(response.status_code, (403, 417))
		self.assertFalse(frappe.db.exists(DOCTYPE, {"title": "Liste ile"}))


class TestPreparedReport(AccessRuleTestCase):
	"""Finding 2: the prepared report path also goes through the gate."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Report", QUERY_REPORT):
			frappe.get_doc(
				doctype="Report",
				report_name=QUERY_REPORT,
				ref_doctype=DOCTYPE,
				report_type="Query Report",
				is_standard="No",
				query=f"select name as `Name:Data:200`, title as `Title:Data:200` from `tab{DOCTYPE}`",
			).insert()
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def setUp(self):
		super().setUp()
		self.addCleanup(self.drop_prepared_reports)
		self.drop_prepared_reports()

	def drop_prepared_reports(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.delete("Prepared Report", {"report_name": QUERY_REPORT})
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_narrowed_user_cannot_queue_a_prepared_report(self):
		frappe.set_user(EMPLOYEE_1)

		self.assertRaises(
			frappe.PermissionError,
			frappe.get_doc({"doctype": "Prepared Report", "report_name": QUERY_REPORT}).insert,
			ignore_permissions=True,
		)

	def test_narrowed_user_cannot_call_the_prepared_report_endpoint(self):
		response = self.send(self.login(EMPLOYEE_1), "POST", PREPARED, body={"report_name": QUERY_REPORT})

		self.assertEqual(response.status_code, 403)
		self.assertFalse(frappe.db.exists("Prepared Report", {"report_name": QUERY_REPORT}))


class TestRuleInput(AccessRuleTestCase):
	"""Findings 5 and 7: an infinite number and a protected document type are denied."""

	def test_non_finite_filter_value_is_rejected(self):
		for raw in ('[["idx", "=", NaN]]', '[["idx", "=", Infinity]]'):
			doc = frappe.get_doc(
				{
					"doctype": RULE_DOCTYPE,
					"title": "Sonsuz",
					"document_type": DOCTYPE,
					"role": ROLE_EMPLOYEE,
					"scope": "all",
					"allow_read": 1,
					"filters": raw,
				}
			)
			self.assertRaises(frappe.ValidationError, doc.insert)

	def drop_rule_field_levels(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.delete("Property Setter", {"doc_type": RULE_DOCTYPE, "property": "permlevel"})
		frappe.db.delete("Custom DocPerm", {"parent": RULE_DOCTYPE})
		frappe.clear_cache(doctype=RULE_DOCTYPE)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_field_level_endpoints_refuse_protected_doctypes(self):
		self.addCleanup(self.drop_rule_field_levels)
		admin = self.login(ADMIN)

		field = self.api(
			admin,
			"POST",
			"set_field_level",
			body={"doctype": RULE_DOCTYPE, "fieldname": "role", "permlevel": 5},
		)
		level = self.api(
			admin,
			"POST",
			"set_level_access",
			body={
				"doctype": RULE_DOCTYPE,
				"role": ROLE_EMPLOYEE,
				"permlevel": 1,
				"read": True,
				"write": False,
			},
		)

		self.assertEqual(field.status_code, 417)
		self.assertEqual(level.status_code, 417)
		self.assertEqual(frappe.get_meta(RULE_DOCTYPE).get_field("role").permlevel, 0)

	def test_explain_refuses_child_tables(self):
		response = self.api(
			self.login(ADMIN), "GET", "explain_permission", query={"doctype": "Has Role", "name": "x"}
		)

		self.assertIn(response.status_code, (403, 417))


class TestOperators(AccessRuleTestCase):
	"""The `!=`, `in` and `not in` operators give the same result in the list and on the single record."""

	RULES = (
		{
			"title": "Calisan kapali olmayan",
			"role": ROLE_EMPLOYEE,
			"scope": "all",
			"filters": '[["status", "!=", "Closed"], ["title", "not in", ["Gizli"]]]',
			"allow_read": 1,
		},
		{
			"title": "IK secili durumlar",
			"role": "ER HR",
			"scope": "all",
			"filters": '[["status", "in", ["Closed"]]]',
			"allow_read": 1,
		},
	)

	def test_operators_select_the_same_records_on_list_and_document(self):
		closed, hidden = self.records[EMPLOYEE_2], self.records[EMPLOYEE_3]
		frappe.db.set_value(DOCTYPE, closed, "status", "Closed")
		frappe.db.set_value(DOCTYPE, hidden, "title", "Gizli")
		employee, hr = self.login(EMPLOYEE_1), self.login(HR)

		expected = set(self.records.values()) - {closed, hidden}
		self.assertEqual(self.listed_names(employee), expected)
		self.assertEqual(self.readable_names(employee), expected)
		self.assertEqual(self.listed_names(hr), {closed})
		self.assertEqual(self.readable_names(hr), {closed})


class TestDepartmentAndCompany(AccessRuleTestCase):
	"""The `department` and `company` scopes (decision note, sections 3 and 7)."""

	RULES = (
		{
			"title": "Calisan bolum kayitlari",
			"role": ROLE_EMPLOYEE,
			"scope": "department",
			"match_field": "employee",
			"allow_read": 1,
		},
		{
			"title": "Yonetici sirket kayitlari",
			"role": "ER Yonetici",
			"scope": "company",
			"match_field": "company",
			"allow_read": 1,
		},
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# ERPNext attaches a department without a parent to the first root. So an explicit root is set up.
		root = cls.department("ER Kok Bolum", None, is_group=1)
		cls.parent = cls.department("ER Ust Bolum", root, is_group=1)
		cls.child = cls.department("ER Alt Bolum", cls.parent)
		cls.other = cls.department("ER Baska Bolum", root)
		for user, department in ((EMPLOYEE_1, cls.parent), (EMPLOYEE_2, cls.child), (EMPLOYEE_3, cls.other)):
			frappe.db.set_value("Employee", employee_of(user), "department", department)
		frappe.db.set_value(DOCTYPE, cls.records[EMPLOYEE_3], "company", None)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("Employee", {"company": COMPANY}, "department", None)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	@classmethod
	def department(cls, title: str, parent: str | None, is_group: int = 0) -> str:
		existing = frappe.db.get_value("Department", {"department_name": title})
		if existing:
			if frappe.db.get_value("Department", existing, "parent_department") == parent:
				return existing
			frappe.delete_doc("Department", existing, force=True)
		doc = frappe.get_doc(
			doctype="Department",
			department_name=title,
			company=COMPANY,
			parent_department=parent,
			is_group=is_group,
		)
		return doc.insert().name

	def test_department_scope_includes_sub_departments(self):
		"""calisan1 is in the parent department. calisan1 also sees the record of calisan2 in the child department."""
		expected = self.names_of([EMPLOYEE_1, EMPLOYEE_2])
		client = self.login(EMPLOYEE_1)

		self.assertEqual(self.listed_names(client), expected)
		self.assertEqual(self.readable_names(client), expected)

	def test_sub_department_does_not_see_the_parent_department(self):
		client = self.login(EMPLOYEE_2)

		self.assertEqual(self.listed_names(client), self.names_of([EMPLOYEE_2]))

	def test_company_scope_excludes_records_of_no_company(self):
		expected = set(self.records.values()) - {self.records[EMPLOYEE_3]}
		client = self.login(MANAGER_1)

		self.assertEqual(self.listed_names(client), expected)
		self.assertEqual(self.readable_names(client), expected)


class TestDeleteAndRename(AccessRuleTestCase):
	def test_role_with_delete_rule_deletes(self):
		name = self.insert_record(EMPLOYEE_1, title="Silinecek")
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

		response = self.rest_delete(self.login(HR), name)

		self.assertIn(response.status_code, (200, 202))
		self.assertFalse(frappe.db.exists(DOCTYPE, name))

	def test_employee_cannot_rename_another_employees_record(self):
		target = self.records[EMPLOYEE_2]

		response = self.send(
			self.login(EMPLOYEE_1),
			"POST",
			"/api/method/frappe.model.rename_doc.update_document_title",
			body={"doctype": DOCTYPE, "docname": target, "name": "ele-gecirildi"},
		)

		self.assertGreaterEqual(response.status_code, 400)
		self.assertTrue(frappe.db.exists(DOCTYPE, target))
