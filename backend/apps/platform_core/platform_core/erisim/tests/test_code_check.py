"""Static check that report and search code reads only through permission-aware calls."""

from frappe.tests import UnitTestCase

from platform_core.erisim import code_check

SAFE = """
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	if not frappe.has_permission("Leave Application", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows = frappe.get_list("Leave Application", fields=["employee", "status"], limit=100)
	return [], [[row.employee, flt(1)] for row in rows]
"""


class TestCodeCheck(UnitTestCase):
	def problems(self, source: str, doctypes=("Leave Application",)) -> list[str]:
		return code_check.problems(source, set(doctypes) if doctypes is not None else None)

	def test_permission_aware_code_passes(self):
		self.assertEqual(self.problems(SAFE), [])

	def test_unsafe_reads_are_reported(self):
		for line in (
			'frappe.db.sql("select 1")',
			'frappe.get_all("Leave Application")',
			'frappe.db.get_value("Leave Application", "x", "status")',
			'frappe.get_doc("Leave Application", "x")',
			'frappe.qb.from_("tabLeave Application")',
			'frappe.get_list("Leave Application", ignore_permissions=True)',
			'frappe.get_list("Leave Application", **{"ignore_permissions": True})',
			'frappe.get_list(*["Leave Application"])',
			'frappe.get_cached_value("Leave Application", "x", "status")',
			'frappe.call("frappe.get_all", "Leave Application")',
			'getattr(frappe, "get_all")("Leave Application")',
			'eval("frappe.db")',
			"db = frappe.db",
			"frappe.local.db.sql('select 1')",
			"frappe.flags.ignore_permissions = True",
			"frappe.set_user('Administrator')",
			"import os",
			"from frappe.model.db_query import DatabaseQuery",
			"from frappe import db",
			"from erpnext.setup.utils import get_exchange_rate",
			"__import__('frappe')",
		):
			with self.subTest(line=line):
				self.assertTrue(self.problems(f"import frappe\n{line}\n"), line)

	def test_reading_an_undeclared_document_type_is_reported(self):
		source = 'import frappe\nrows = frappe.get_list("Salary Slip")\n'

		self.assertTrue(self.problems(source))
		self.assertEqual(self.problems(source, ("Salary Slip",)), [])

	def test_document_type_must_be_a_literal_or_the_search_argument(self):
		computed = 'import frappe\nname = "Salary" + " Slip"\nrows = frappe.get_list(name)\n'
		search = "import frappe\ndef query(doctype, txt):\n\treturn frappe.get_list(doctype)\n"

		self.assertTrue(self.problems(computed))
		self.assertEqual(self.problems(search, None), [])

	def test_code_that_does_not_parse_is_reported(self):
		self.assertTrue(self.problems("def broken(:\n"))
		self.assertTrue(self.problems(""))
