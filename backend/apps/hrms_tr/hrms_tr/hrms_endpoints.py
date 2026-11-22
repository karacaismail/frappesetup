"""Close legacy HRMS RPC routes that do not enforce HRMS TR leave access."""

import frappe
from frappe import _


# The route never reads a document and always raises PermissionError.
# nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
@frappe.whitelist(methods=["GET", "POST"])
def deny_legacy_leave_query():
	frappe.throw(_("Read leave information through an authorized leave application."), frappe.PermissionError)


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


class PreparedReportAccess:
	"""Prevent downloads of older results for the blocked reports."""

	def get_prepared_data(self, with_file_name=False):
		from frappe.desk.query_report import get_reference_report

		name = self.report_name
		if name not in BLOCKED_LEAVE_REPORTS:
			name = get_reference_report(frappe.get_cached_doc("Report", name)).name
		if name in BLOCKED_LEAVE_REPORTS:
			deny_legacy_leave_query()
		return super().get_prepared_data(with_file_name=with_file_name)
