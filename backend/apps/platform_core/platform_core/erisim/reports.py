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
- Auto Email Report on governed data is for System Managers only, the report rules also hold
  for the user named on the record, and a record runs only while a System Manager's approval
  of its current settings is on file. The engine never switches the session user.

Every way to get report data ends in `Report.execute_query_report` or
`Report.execute_script_report` (`frappe/desk/query_report.py:93`). `GuardedReport` extends the
Report document through the `extend_doctype_class` hook, so a request, a background export
and code that calls Frappe directly all meet the same check.
Decision note: `docs/kararlar/0006-erisim-kurali.md`, section 9.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime

from platform_core.erisim import rules

ADMIN_ROLE = "System Manager"
PREPARED_REPORT = "Prepared Report"
AUTO_EMAIL_REPORT = "Auto Email Report"
APPROVAL = "Auto Email Report Approval"
REPORT_FIELDS = ["name", "ref_doctype", "report_type", "reference_report"]


def any_governed() -> bool:
	return bool(rules.active_rules())


def report_record(report_name: str):
	"""The Report row that decides. A custom report uses the data of the report it refers to."""
	record = frappe.db.get_value("Report", report_name, REPORT_FIELDS, as_dict=True)
	if record and record.reference_report and record.reference_report != report_name:
		return report_record(record.reference_report)
	return record


def touches_governed(report_name: str | None, governed: set[str] | None = None) -> bool:
	"""Does the report read a governed document type, or may it for all we know?

	`governed` replaces the engine's own list of governed types. Migration passes it, because
	the engine does not read rules on its own while a site is being migrated.
	"""
	governed = set(rules.active_rules()) if governed is None else governed
	record = report_record(report_name) if report_name else None
	if not record or not governed:
		return False
	if record.report_type == "Report Builder":
		return record.ref_doctype in governed
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


PREPARED_REPORT_JOB = "prepared_report.generate_report"


def refuse_inside_prepared_report_job(report_name: str) -> None:
	"""Refuse when a worker is building a Prepared Report for a report that touches governed data.

	The job calls neither `before_insert` nor `get_prepared_data`
	(`frappe/core/doctype/prepared_report/prepared_report.py:107`). A record queued before the
	rule existed would still run. The worker names the running method in `frappe.local.job`
	(`frappe/utils/background_jobs.py:260`).
	"""
	job = getattr(frappe.local, "job", None)
	if job and str(job.get("method") or "").endswith(PREPARED_REPORT_JOB):
		refuse_prepared_report(report_name)


class GuardedReport:
	"""Extension of Report: no data is read before the gate agrees."""

	def execute_query_report(self, filters):
		refuse_inside_prepared_report_job(self.name)
		guard(self.name)
		return super().execute_query_report(filters)

	def execute_script_report(self, filters):
		refuse_inside_prepared_report_job(self.name)
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


def is_system_manager(user: str) -> bool:
	return user == "Administrator" or ADMIN_ROLE in frappe.get_roles(user)


def value_fields() -> list[str]:
	"""Fields of Auto Email Report that hold its settings."""
	meta = frappe.get_meta(AUTO_EMAIL_REPORT)
	return sorted(set(meta.get_valid_columns()) - set(frappe.model.default_fields))


def settings_digest(name: str | None) -> str | None:
	"""Fingerprint of the saved settings of an Auto Email Report. None when it is not saved.

	It is taken from the database row, so it describes the record that will run, not a copy in
	memory. Every settings field counts: report, user, recipients, filters, format and the rest.
	"""
	if not name:
		return None
	fieldnames = value_fields()
	# The engine's own read of one row it was asked about (exception to G-3).
	row = frappe.db.get_value(AUTO_EMAIL_REPORT, name, fieldnames, as_dict=True)
	if not row:
		return None
	text = "\x1f".join(f"{fieldname}={cstr(row.get(fieldname))}" for fieldname in fieldnames)
	return hashlib.sha256(text.encode()).hexdigest()


def approval_is_valid(name: str | None) -> bool:
	"""Did a System Manager approve exactly the settings the record has now?"""
	if not name:
		return False
	approval = frappe.db.get_value(APPROVAL, name, ["approved_by", "settings_digest"], as_dict=True)
	if not approval or not is_system_manager(approval.approved_by):
		return False
	return approval.settings_digest == settings_digest(name)


def record_approval(name: str) -> None:
	"""Keep who approved the record and when. Called when a System Manager saves it by hand."""
	approval = (
		frappe.get_doc(APPROVAL, name) if frappe.db.exists(APPROVAL, name) else frappe.new_doc(APPROVAL)
	)
	approval.update(
		{
			"auto_email_report": name,
			"approved_by": frappe.session.user,
			"approved_on": now_datetime(),
			"settings_digest": settings_digest(name),
		}
	)
	approval.save()


def switch_off_unapproved_auto_email_reports() -> None:
	"""Switch off every Auto Email Report on governed data that has no valid approval.

	Runs after install and after migrate. A record saved before the rule existed may have been
	set up by someone who is no System Manager. It comes back only when a System Manager saves
	it by hand, which records the approval.
	"""
	if not frappe.db.table_exists(rules.RULE_DOCTYPE) or not frappe.db.table_exists(APPROVAL):
		return
	governed = set(rules.load_now())
	if not governed:
		return
	# System maintenance over every record, not a read for a user (exception to G-3).
	for row in frappe.get_all(AUTO_EMAIL_REPORT, filters={"enabled": 1}, fields=["name", "report"]):
		if touches_governed(row.report, governed) and not approval_is_valid(row.name):
			frappe.db.set_value(AUTO_EMAIL_REPORT, row.name, "enabled", 0)


class GuardedAutoEmailReport:
	"""Extension of Auto Email Report: on governed data it is for System Managers only.

	The record runs a report later, for a user who is not present, and mails the result. The
	project runs no scheduled jobs (D-6), so the rule is as narrow as it can be.

	Saving. The user who saves must be a System Manager when the record's report, or the
	report it had before, touches governed data. The report rules must also allow the report
	for the user named on the record. Frappe lets a Report Manager save such a record and
	choose any user for it (`frappe/email/doctype/auto_email_report/auto_email_report.json`).

	Running. Download, send now and the scheduler all need the same, and also a valid
	approval. The scheduler works as Administrator (`frappe/utils/scheduler.py:117`), so the
	session user proves nothing there. A System Manager saving the record by hand is the
	approval. A record changed afterwards, or saved before the rule existed, does not run.

	The engine never switches the session user: `frappe.set_user` resets the session data and
	the request input (`frappe/__init__.py:381`). Frappe passes the record's user to a list
	report as the user to read for; a query or script report reads as the session user.
	"""

	def refuse_on_governed_data(self, previous_report: str | None = None) -> None:
		governed = touches_governed(self.report) or touches_governed(previous_report)
		if governed and not is_system_manager(frappe.session.user):
			frappe.throw(
				_(
					"Only a System Manager may use Auto Email Report for {0}: it reads data governed by Access Rules."
				).format(frappe.bold(previous_report or self.report)),
				frappe.PermissionError,
			)
		guard(self.report, self.user)

	def refuse_without_approval(self) -> None:
		if touches_governed(self.report) and not approval_is_valid(self.name):
			frappe.throw(
				_(
					"Auto Email Report {0} is not approved. A System Manager must save it before it can run."
				).format(frappe.bold(self.name or self.report)),
				frappe.PermissionError,
			)

	def validate(self):
		previous = None if self.is_new() else frappe.db.get_value(AUTO_EMAIL_REPORT, self.name, "report")
		self.refuse_on_governed_data(previous)
		return super().validate()

	def on_update(self):
		in_job = bool(getattr(frappe.local, "job", None))
		if touches_governed(self.report) and is_system_manager(frappe.session.user) and not in_job:
			record_approval(self.name)
		# The Frappe class has no `on_update` today. Another extension in the chain may.
		parent = getattr(super(), "on_update", None)
		return parent() if parent else None

	def get_report_content(self):
		self.refuse_on_governed_data()
		self.refuse_without_approval()
		return super().get_report_content()

	def send(self):
		self.refuse_on_governed_data()
		self.refuse_without_approval()
		return super().send()


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
