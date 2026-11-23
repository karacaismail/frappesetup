"""Close legacy HRMS RPC routes that do not enforce HRMS TR leave access."""

from typing import Never

import frappe
from frappe import _


# The route never reads a document and always raises PermissionError.
# nosemgrep: backend.dev.security.fixtures.frappe-missing-permission
@frappe.whitelist(methods=["GET", "POST"])
def deny_legacy_leave_query() -> Never:
	frappe.throw(
		_("Read leave information through an authorized leave application.", context="hrms_tr"),
		frappe.PermissionError,
	)


BLOCKED_LEAVE_REPORTS = frozenset(
	("Employee Leave Balance", "Employee Leave Balance Summary", "Leave Ledger")
)


class ReportAccess:
	"""Veto HRMS reports that cannot apply the site's Leave Application policy."""

	def is_permitted(self):
		if self.name in BLOCKED_LEAVE_REPORTS:
			return False
		return super().is_permitted()

	def execute_script_report(self, filters):
		# Previously queued prepared reports can bypass is_permitted().
		if self.name in BLOCKED_LEAVE_REPORTS:
			deny_legacy_leave_query()
		return super().execute_script_report(filters)


class AttendanceRequestAccess:
	"""Keep warnings available internally without exposing them as document RPC."""

	def get_attendance_warnings(self):
		return super().get_attendance_warnings()


def is_blocked_report(name):
	"""Resolve custom report aliases using the same rules as the native runner."""
	if name in BLOCKED_LEAVE_REPORTS:
		return True
	from frappe.desk.query_report import get_reference_report

	return get_reference_report(frappe.get_cached_doc("Report", name)).name in BLOCKED_LEAVE_REPORTS


class PreparedReportAccess:
	"""Prevent downloads of older results for the blocked reports."""

	def get_prepared_data(self, with_file_name=False):
		if is_blocked_report(self.report_name):
			deny_legacy_leave_query()
		return super().get_prepared_data(with_file_name=with_file_name)


class PreparedReportFileAccess:
	"""Apply the report restriction to direct private file downloads."""

	def is_downloadable(self):
		if self.attached_to_doctype == "Prepared Report" and self.attached_to_name:
			name = frappe.db.get_value("Prepared Report", self.attached_to_name, "report_name")
			if not name or is_blocked_report(name):
				return False
		return super().is_downloadable()
