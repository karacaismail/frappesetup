"""Report gate.

Query and script reports read data with their own SQL or code. They do not pass the list hook
and Frappe does not remove fields by permission level there (`frappe/desk/query_report.py:968`).
The gate decides before any data is read whether the report may run for the user.

Rules while any document type is governed (decisions of the third review):

- Report builder reports read through `frappe.get_list`. They run; Frappe applies the rules.
- A query report runs only for a System Manager. What its SQL reads cannot be verified.
- A script report runs only when an app declared what it reads and its code reads through
  permission-aware calls only. The code is checked again on every execution.
- Prepared Report is closed for a report that touches governed data.
- Auto Email Report follows the same rules for the user it runs as.

Every way to get report data ends in `Report.execute_query_report` or
`Report.execute_script_report` (`frappe/desk/query_report.py:93`). `GuardedReport` extends the
Report document through the `extend_doctype_class` hook, so a request, a background export
and code that calls Frappe directly all meet the same check.
Decision note: `docs/kararlar/0006-erisim-kurali.md`, section 9.
"""

import inspect

import frappe
from frappe import _
from frappe.core.doctype.report.report import get_report_module_dotted_path
from frappe.permissions import get_role_permissions

from platform_core.erisim import code_check, rules

SCOPES_HOOK = "access_rule_report_scopes"
ADMIN_ROLE = "System Manager"
PREPARED_REPORT = "Prepared Report"
REPORT_FIELDS = ["name", "ref_doctype", "report_type", "reference_report", "is_standard", "module"]


def any_governed() -> bool:
	return bool(rules.active_rules())


def declared_hook(report_name: str) -> dict | None:
	"""What apps declared for the report in `access_rule_report_scopes`, merged.

	`access_rule_report_scopes = {"Report Name": {"Document Type": ["field", ...]}}`
	"""
	hook = frappe.get_hooks(SCOPES_HOOK)
	declarations = hook.get(report_name) if isinstance(hook, dict) else None
	if not declarations:
		return None
	merged: dict = {}
	for declaration in declarations:
		if not isinstance(declaration, dict):
			return {}
		for doctype, fields in declaration.items():
			merged.setdefault(doctype, [])
			merged[doctype] += list(fields or [])
	return merged


def declared_scope(report_name: str) -> dict[str, list[str]] | None:
	"""The declared document types and fields, or None when the declaration cannot be used.

	A missing, empty or incomplete declaration is no declaration: every document type must
	exist and must name at least one real field. `*` is not accepted.
	"""
	scope = declared_hook(report_name)
	if not scope or not isinstance(scope, dict):
		return None
	for doctype, fields in scope.items():
		if not fields or not frappe.db.exists("DocType", doctype, cache=True):
			return None
		columns = set(frappe.get_meta(doctype).get_valid_columns())
		if any(fieldname not in columns for fieldname in fields):
			return None
	return scope


def report_record(report_name: str):
	"""The Report row that decides. A custom report uses the data of the report it refers to."""
	record = frappe.db.get_value("Report", report_name, REPORT_FIELDS, as_dict=True)
	if record and record.reference_report and record.reference_report != report_name:
		return report_record(record.reference_report)
	return record


def report_source(record) -> str | None:
	"""The code of a script report as it is now: the app module, or the script kept on the record."""
	if record.is_standard != "Yes":
		return frappe.db.get_value("Report", record.name, "report_script")
	module = record.module or frappe.db.get_value("DocType", record.ref_doctype, "module")
	try:
		return inspect.getsource(frappe.get_module(get_report_module_dotted_path(module, record.name)))
	except (ImportError, OSError, TypeError):
		return None


def script_report_problem(record) -> str | None:
	"""Why a script report cannot be trusted with governed data, or None when it can."""
	scope = declared_scope(record.name)
	if scope is None:
		return _("Report {0} does not declare what it reads.").format(frappe.bold(record.name))
	found = code_check.problems(report_source(record), set(scope))
	if found:
		return _("Report {0} does not read through permission-aware calls only: {1}").format(
			frappe.bold(record.name), ", ".join(found)
		)
	return None


def touches_governed(report_name: str) -> bool:
	"""Does the report read a governed document type, or may it for all we know?"""
	record = report_record(report_name)
	if not record or not any_governed():
		return False
	if record.report_type == "Report Builder":
		return rules.is_governed(record.ref_doctype)
	if record.report_type == "Script Report" and not script_report_problem(record):
		touched = {record.ref_doctype, *declared_scope(record.name)}
		return any(rules.is_governed(doctype) for doctype in touched)
	# A query report, or a script report the engine cannot read: assume the worst.
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

	if record.report_type != "Script Report":
		if ADMIN_ROLE in frappe.get_roles(user):
			return None
		return _(
			"Report {0} runs its own SQL. Only a System Manager may run it while Access Rules exist."
		).format(frappe.bold(record.name))

	problem = script_report_problem(record)
	if problem:
		return problem
	for doctype in declared_scope(record.name):
		if not get_role_permissions(frappe.get_meta(doctype), user=user).get("read"):
			return _("Report {0} reads {1}, which you may not read.").format(
				frappe.bold(record.name), frappe.bold(doctype)
			)
	return None


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
	"""Extension of Auto Email Report: the report rules apply to the user the record runs as."""

	def validate(self):
		guard(self.report, self.user)
		return super().validate()

	def get_report_content(self):
		guard(self.report, self.user)
		return super().get_report_content()


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
