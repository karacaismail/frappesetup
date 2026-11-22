"""Report gate.

Query and script reports read data with their own SQL or code. They do not pass the list hook
and Frappe does not remove fields by permission level there (`frappe/desk/query_report.py:968`).
The gate therefore decides before any data is read whether the report may run for the user.

Every way to get report data ends in `Report.execute_query_report` or
`Report.execute_script_report` (`frappe/desk/query_report.py:93`). `GuardedReport` extends the
Report document through the `extend_doctype_class` hook, so the request, a background export,
a prepared report job and code that calls Frappe directly all meet the same check.
Decision note: `docs/kararlar/0006-erisim-kurali.md`, section 9.
"""

import frappe
from frappe import _
from frappe.permissions import get_role_permissions

from platform_core.erisim import rules

AWARE_REPORTS_HOOK = "access_rule_aware_reports"
SCOPES_HOOK = "access_rule_report_scopes"
ALL_FIELDS = "*"
PREPARED_REPORT = "Prepared Report"


def declared_scope(report_name: str) -> dict[str, list[str]] | None:
	"""Document types and fields a report says it reads. None when the report declares nothing.

	An app declares it in `hooks.py`:
	`access_rule_report_scopes = {"Report Name": {"Document Type": ["field", ...]}}`.
	The field list `["*"]` means every field of that document type.
	"""
	declarations = (frappe.get_hooks(SCOPES_HOOK) or {}).get(report_name)
	if not declarations:
		return None
	scope: dict[str, list[str]] = {}
	for declaration in declarations:
		for doctype, fields in (declaration or {}).items():
			scope.setdefault(doctype, []).extend(fields or [ALL_FIELDS])
	return scope


def sees_every_record(doctype: str, user: str) -> bool:
	"""Is the user unrestricted by record on this document type?"""
	if not rules.is_governed(doctype):
		return True
	return any(
		rule["scope"] == "all" and not rule["filters"] for rule in rules.applicable(doctype, user, "read")
	)


def reads_fields(doctype: str, fields: list[str], user: str) -> bool:
	"""Does the user hold read access at the permission level of each field?"""
	meta = frappe.get_meta(doctype)
	if ALL_FIELDS in fields:
		docfields = list(meta.fields)
		for table_field in meta.get_table_fields():
			docfields += frappe.get_meta(table_field.options).fields
	else:
		docfields = [meta.get_field(fieldname) for fieldname in fields]
		if None in docfields:
			# A declared field that is not a field of the type is treated as unreadable.
			standard = set(frappe.model.default_fields) | {"name"}
			if any(
				df is None and fieldname not in standard
				for df, fieldname in zip(docfields, fields, strict=True)
			):
				return False
			docfields = [df for df in docfields if df is not None]
	used = {df.permlevel for df in docfields if df.permlevel}
	return used <= set(meta.get_permlevel_access("read", user=user))


def touched_doctypes(report_name: str) -> dict[str, list[str]] | None:
	"""Document types the report reads, with their fields. None when the report checks access itself.

	A report builder report reads through `frappe.get_list`, so only its own type is touched and
	Frappe applies record rules and field levels. For a query or script report of unknown scope
	the answer is its own type plus every governed type, each with every field.
	"""
	report = frappe.db.get_value(
		"Report", report_name, ["ref_doctype", "report_type", "reference_report"], as_dict=True
	)
	if not report:
		return {}
	if report.reference_report:
		# A custom report uses the data of another report. That report decides.
		return touched_doctypes(report.reference_report)
	if report.report_type == "Report Builder" or report_name in (frappe.get_hooks(AWARE_REPORTS_HOOK) or []):
		return None
	scope = declared_scope(report_name)
	if scope is None:
		scope = {doctype: [ALL_FIELDS] for doctype in rules.active_rules()}
		scope[report.ref_doctype] = [ALL_FIELDS]
	return scope


def touches_governed(report_name: str) -> bool:
	"""Does the report read a governed document type, or may it for all we know?"""
	touched = touched_doctypes(report_name)
	if touched is None:
		ref_doctype = frappe.db.get_value("Report", report_name, "ref_doctype")
		return bool(ref_doctype) and rules.is_governed(ref_doctype)
	return any(rules.is_governed(doctype) for doctype in touched)


def denial(report_name: str | None, user: str | None = None) -> str | None:
	"""Return why the user may not get this report's data, or None when the report is allowed."""
	user = user or frappe.session.user
	if user == "Administrator" or not report_name:
		return None
	touched = touched_doctypes(report_name)
	if not touched:
		return None
	for doctype, fields in touched.items():
		if not frappe.db.exists("DocType", doctype, cache=True):
			return _("Report {0} declares an unknown document type.").format(frappe.bold(report_name))
		if not get_role_permissions(frappe.get_meta(doctype), user=user).get("read"):
			return _("Report {0} reads {1}, which you may not read.").format(
				frappe.bold(report_name), frappe.bold(doctype)
			)
		if not sees_every_record(doctype, user):
			return _("Report {0} cannot apply the Access Rules of {1}.").format(
				frappe.bold(report_name), frappe.bold(doctype)
			)
		if not reads_fields(doctype, fields, user):
			return _("Report {0} cannot apply the field levels of {1}.").format(
				frappe.bold(report_name), frappe.bold(doctype)
			)
	return None


def guard(report_name: str | None, user: str | None = None) -> None:
	"""Raise a permission error when the report cannot honour the user's record and field limits."""
	reason = denial(report_name, user)
	if reason:
		frappe.throw(reason, frappe.PermissionError)


def prepared_report_denial(prepared_report: str | None, user: str | None = None) -> str | None:
	"""A stored report result is as sensitive as running the report now."""
	report_name = frappe.db.get_value(PREPARED_REPORT, prepared_report, "report_name")
	return denial(report_name, user) if report_name else None


def guard_prepared_report(doc, method=None) -> None:
	"""Runs before a Prepared Report is queued, so a refusal is reported at once."""
	guard(doc.report_name)


class GuardedReport:
	"""Extension of the Report document: no data is read before the gate agrees."""

	def execute_query_report(self, filters):
		guard(self.name)
		return super().execute_query_report(filters)

	def execute_script_report(self, filters):
		guard(self.name)
		return super().execute_script_report(filters)


class GuardedAutoEmailReport:
	"""Extension of Auto Email Report: it may not touch governed data.

	The record runs later, as its `user`, without that user being present. The project does not
	run scheduled jobs (D-6), so the safe choice is to refuse both saving and running it.
	"""

	def refuse_governed_data(self) -> None:
		if touches_governed(self.report):
			frappe.throw(
				_("Auto Email Report cannot be used for {0}: it reads data governed by Access Rules.").format(
					frappe.bold(self.report)
				),
				frappe.PermissionError,
			)

	def validate(self):
		self.refuse_governed_data()
		super().validate()

	def get_report_content(self):
		self.refuse_governed_data()
		return super().get_report_content()


class GuardedFile:
	"""Extension of File: a prepared report file follows the reader's current access.

	Frappe lets the owner of a file, and anyone it is shared with, download it without asking the
	attached document (`frappe/core/doctype/file/file.py:1097`). For a prepared report that would
	keep old data readable after access was narrowed.
	"""

	def is_downloadable(self):
		if self.attached_to_doctype == PREPARED_REPORT and prepared_report_denial(self.attached_to_name):
			return False
		return super().is_downloadable()
