"""Report gate.

Query and script reports read data with their own SQL or code. They do not pass the list hook
and Frappe does not remove fields by permission level there (`frappe/desk/query_report.py:968`).
The gate decides before any data is read whether the report may run for the user.

Rules while any document type is governed:

- Report builder reports read through `frappe.get_list`. They run; Frappe applies the rules.
- A query report and a script report run only for a System Manager. What their SQL or code
  reads cannot be verified. A static check of script code was tried and removed: an aliased
  import or a `user` argument got around it, and such a check can never be complete.
- Prepared Report is closed for a report that touches governed data.
- Auto Email Report follows the same rules for the user it runs as, and runs as that user.

Every way to get report data ends in `Report.execute_query_report` or
`Report.execute_script_report` (`frappe/desk/query_report.py:93`). `GuardedReport` extends the
Report document through the `extend_doctype_class` hook, so a request, a background export
and code that calls Frappe directly all meet the same check.
Decision note: `docs/kararlar/0006-erisim-kurali.md`, section 9.
"""

import frappe
from frappe import _

from platform_core.erisim import rules

ADMIN_ROLE = "System Manager"
PREPARED_REPORT = "Prepared Report"
REPORT_FIELDS = ["name", "ref_doctype", "report_type", "reference_report"]


def any_governed() -> bool:
	return bool(rules.active_rules())


def report_record(report_name: str):
	"""The Report row that decides. A custom report uses the data of the report it refers to."""
	record = frappe.db.get_value("Report", report_name, REPORT_FIELDS, as_dict=True)
	if record and record.reference_report and record.reference_report != report_name:
		return report_record(record.reference_report)
	return record


def touches_governed(report_name: str) -> bool:
	"""Does the report read a governed document type, or may it for all we know?"""
	record = report_record(report_name)
	if not record or not any_governed():
		return False
	if record.report_type == "Report Builder":
		return rules.is_governed(record.ref_doctype)
	# A query or script report may read any table. Its own document type proves nothing.
	return True


def reads_every_field(doctype: str, user: str) -> bool:
	"""Does the user hold read access at every permission level the document type uses?"""
	meta = frappe.get_meta(doctype)
	fields = list(meta.fields)
	for table_field in meta.get_table_fields():
		fields += frappe.get_meta(table_field.options).fields
	used = {df.permlevel for df in fields if df.permlevel}
	return used <= set(meta.get_permlevel_access("read", user=user))


def denial(report_name: str | None, user: str | None = None) -> str | None:
	"""Return why the user may not get this report's data, or None when the report is allowed."""
	user = user or frappe.session.user
	if user == "Administrator" or not report_name:
		return None
	record = report_record(report_name)
	if not record or record.report_type == "Report Builder":
		return None

	if not any_governed():
		# No record rule exists. The field level of the report's own type is still kept.
		if not reads_every_field(record.ref_doctype, user):
			return _("Report {0} cannot apply the field levels of {1}.").format(
				frappe.bold(record.name), frappe.bold(record.ref_doctype)
			)
		return None

	if ADMIN_ROLE in frappe.get_roles(user):
		return None
	return _(
		"Report {0} reads data with its own code. Only a System Manager may run it while Access Rules exist."
	).format(frappe.bold(record.name))


def guard(report_name: str | None, user: str | None = None) -> None:
	"""Raise a permission error when the report may not run for the user."""
	reason = denial(report_name, user)
	if reason:
		frappe.throw(reason, frappe.PermissionError)


def prepared_report_closed(prepared_report: str | None) -> bool:
	"""Is this stored result closed because its report touches governed data?"""
	report_name = frappe.db.get_value(PREPARED_REPORT, prepared_report, "report_name")
	return bool(report_name) and touches_governed(report_name)


def refuse_prepared_report(report_name: str | None) -> None:
	if report_name and touches_governed(report_name):
		frappe.throw(
			_(
				"Prepared Report is switched off for {0}: the report reads data governed by Access Rules."
			).format(frappe.bold(report_name)),
			frappe.PermissionError,
		)


# The classes below extend Frappe documents through `extend_doctype_class`. Frappe puts them in
# front of the document class and of the extensions of other apps (`frappe/model/document.py:207`).
# Every method calls `super()` so the next class in that chain still runs.


class GuardedReport:
	"""Extension of Report: no data is read before the gate agrees."""

	def execute_query_report(self, filters):
		guard(self.name)
		return super().execute_query_report(filters)

	def execute_script_report(self, filters):
		guard(self.name)
		return super().execute_script_report(filters)


class GuardedPreparedReport:
	"""Extension of Prepared Report: the feature is off for reports that touch governed data.

	A stored result is a copy of data taken at another time, for another user. The engine
	cannot narrow it afterwards, so it is neither made nor read. This holds for every user.
	"""

	def before_insert(self):
		refuse_prepared_report(self.report_name)
		return super().before_insert()

	def get_prepared_data(self, with_file_name=False):
		refuse_prepared_report(self.report_name)
		return super().get_prepared_data(with_file_name=with_file_name)


class GuardedAutoEmailReport:
	"""Extension of Auto Email Report: the report rules apply to the user the record runs as.

	Frappe hands `self.user` to the report as an argument but keeps the session of whoever
	downloads or sends the record (`frappe/email/doctype/auto_email_report/auto_email_report.py:152`).
	Record rules and field levels follow the session user. So the report is run as `self.user`,
	and the previous user is put back even when the report fails.
	"""

	def validate(self):
		guard(self.report, self.user)
		return super().validate()

	def get_report_content(self):
		guard(self.report, self.user)
		previous_user = frappe.session.user
		frappe.set_user(self.user)
		try:
			return super().get_report_content()
		finally:
			frappe.set_user(previous_user)


class GuardedFile:
	"""Extension of File: the file of a closed prepared report cannot be read.

	Frappe lets the owner of a file, and anyone it is shared with, read it without asking the
	attached document (`frappe/core/doctype/file/file.py:1097`). These two methods are asked
	before that: `is_downloadable` for the private file path, `get_content` for everything that
	reads the bytes, such as the ZIP download.
	"""

	def _is_closed_prepared_report(self) -> bool:
		return self.attached_to_doctype == PREPARED_REPORT and prepared_report_closed(self.attached_to_name)

	def is_downloadable(self):
		if self._is_closed_prepared_report():
			return False
		return super().is_downloadable()

	def get_content(self, *args, **kwargs):
		if self._is_closed_prepared_report():
			frappe.throw(
				_("This file belongs to a prepared report that is switched off."), frappe.PermissionError
			)
		return super().get_content(*args, **kwargs)
