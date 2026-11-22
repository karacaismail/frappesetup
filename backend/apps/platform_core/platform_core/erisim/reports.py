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
- Auto Email Report is switched off for a report that touches governed data. Nobody can
  create, enable, download or send such a record. The engine never switches the session user.

Every way to get report data ends in `Report.execute_query_report` or
`Report.execute_script_report` (`frappe/desk/query_report.py:93`). `GuardedReport` extends the
Report document through the `extend_doctype_class` hook, so a request, a background export
and code that calls Frappe directly all meet the same check.
Decision note: `docs/kararlar/0006-erisim-kurali.md`, section 9.
"""

import frappe
from frappe import _
from frappe.utils import cint

from platform_core.erisim import rules

ADMIN_ROLE = "System Manager"
PREPARED_REPORT = "Prepared Report"
AUTO_EMAIL_REPORT = "Auto Email Report"
REPORT_FIELDS = ["name", "ref_doctype", "report_type", "reference_report"]


def any_governed() -> bool:
	return bool(rules.active_rules())


CUSTOM_REPORT = "Custom Report"


def report_record(report_name: str | None):
	"""The Report row Frappe will really run, and whether it could be found.

	Frappe follows `reference_report` only for a report of type "Custom Report"
	(`frappe/desk/query_report.py:240`). A report of another type runs itself, also when the
	field still holds an old value. Returns `(row, True)` for the report that runs,
	`(None, True)` when the named report does not exist, and `(None, False)` when a custom
	report refers to a missing report or the references form a loop.
	"""
	seen: set[str] = set()
	name = report_name
	while name and name not in seen:
		seen.add(name)
		record = frappe.db.get_value("Report", name, REPORT_FIELDS, as_dict=True)
		if not record:
			# The first name being unknown is Frappe's business. A broken reference is ours.
			return None, len(seen) == 1
		if record.report_type != CUSTOM_REPORT:
			return record, True
		name = record.reference_report
	return None, not seen


def touches_governed(report_name: str | None, governed: set[str] | None = None) -> bool:
	"""Does the report read a governed document type, or may it for all we know?

	`governed` replaces the engine's own list of governed types. Migration passes it, because
	the engine does not read rules on its own while a site is being migrated.
	"""
	governed = set(rules.active_rules()) if governed is None else governed
	record, resolved = report_record(report_name)
	if not governed:
		return False
	if not resolved:
		# Nobody can tell what would run. Assume the worst.
		return True
	if not record:
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
	record, resolved = report_record(report_name)
	if not resolved:
		return _("Report {0} refers to a report that cannot be found.").format(frappe.bold(report_name))
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


def refuse_prepared_report_job(method: str | None = None, kwargs: dict | None = None, **_ignored) -> None:
	"""`before_job` hook: stop a queued Prepared Report job before Frappe starts it.

	A record queued before the rule existed passes neither `before_insert` nor
	`get_prepared_data` (`frappe/core/doctype/prepared_report/prepared_report.py:107`). The
	worker calls every `before_job` hook before the job function
	(`frappe/utils/background_jobs.py:269`). The check is done here for every report type: a
	list report never reaches the gate inside the Report document.
	"""
	if not str(method or "").endswith(PREPARED_REPORT_JOB):
		return
	name = (kwargs or {}).get("prepared_report")
	report_name = frappe.db.get_value(PREPARED_REPORT, name, "report_name") if name else None
	if not report_name or not touches_governed(report_name):
		return
	reason = _(
		"Prepared Report is switched off for {0}: the report reads data governed by Access Rules."
	).format(frappe.bold(report_name))
	# The job never starts, so nothing else would mark the record. Without this it stays queued.
	frappe.db.set_value(PREPARED_REPORT, name, {"status": "Error", "error_message": reason})
	frappe.db.commit()
	frappe.throw(reason, frappe.PermissionError)


def refuse_inside_prepared_report_job(report_name: str) -> None:
	"""Second check inside the Report document, for a job started without the worker's hooks."""
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


def switch_off_governed_auto_email_reports() -> None:
	"""Switch off every enabled Auto Email Report that touches governed data.

	Runs after install and after migrate. The records are kept, only `enabled` is cleared.
	They cannot be enabled again while their report touches governed data.
	"""
	if not frappe.db.table_exists(rules.RULE_DOCTYPE):
		return
	governed = set(rules.load_now())
	if not governed:
		return
	# System maintenance over every record, not a read for a user (exception to G-3).
	for row in frappe.get_all(AUTO_EMAIL_REPORT, filters={"enabled": 1}, fields=["name", "report"]):
		if touches_governed(row.report, governed):
			frappe.db.set_value(AUTO_EMAIL_REPORT, row.name, "enabled", 0)


class GuardedAutoEmailReport:
	"""Extension of Auto Email Report: switched off for reports that touch governed data.

	The record runs a report later, without a user being present, and mails the result. The
	project runs no scheduled jobs (D-6) and the first release needs no email reports. Rules
	for who may save, whose data is read and who approved were tried; every review found a new
	gap in them. So the feature is simply off, for every user and for the scheduler:

	- such a record cannot be created, and an existing one cannot be enabled;
	- it cannot be downloaded or sent, by hand or by the scheduler.

	An existing record can still be saved while it stays switched off, and it can be deleted.
	The engine never switches the session user (`frappe.set_user` resets the session,
	`frappe/__init__.py:381`).
	"""

	def refuse_on_governed_data(self) -> None:
		if touches_governed(self.report):
			frappe.throw(
				_(
					"Auto Email Report is switched off for {0}: the report reads data governed by Access Rules."
				).format(frappe.bold(self.report)),
				frappe.PermissionError,
			)

	def validate(self):
		# `is_new` is set only by `insert`. A record that is not in the database is new as well.
		is_new = self.is_new() or not (self.name and frappe.db.exists(AUTO_EMAIL_REPORT, self.name))
		if is_new or cint(self.enabled):
			self.refuse_on_governed_data()
		if not touches_governed(self.report):
			guard(self.report, self.user)
		return super().validate()

	def get_report_content(self):
		self.refuse_on_governed_data()
		return super().get_report_content()

	def send(self):
		self.refuse_on_governed_data()
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

	def before_insert(self):
		if self._is_closed_prepared_report():
			frappe.throw(
				_("This file belongs to a prepared report that is switched off."), frappe.PermissionError
			)
		parent = getattr(super(), "before_insert", None)
		return parent() if parent else None

	def get_content(self, *args, **kwargs):
		if self._is_closed_prepared_report():
			frappe.throw(
				_("This file belongs to a prepared report that is switched off."), frappe.PermissionError
			)
		return super().get_content(*args, **kwargs)
