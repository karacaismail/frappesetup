app_name = "hrms_tr"
app_title = "HRMS TR"
app_publisher = "HRMS TR"
app_description = "Leave application workflow"
app_email = "dev@example.test"
app_license = "GPL-3.0-only"

required_apps = ["hrms", "platform_core"]

before_install = "hrms_tr.setup.check_install"
before_migrate = "hrms_tr.setup.before_migrate"
after_migrate = "hrms_tr.setup.after_migrate"
before_uninstall = "hrms_tr.setup.before_uninstall"
after_uninstall = "hrms_tr.setup.after_uninstall"

ai_tools = ["hrms_tr.ai_tools.declarations"]
permission_query_conditions = {"Leave Application": "hrms_tr.access.query_condition"}
has_permission = {"Leave Application": "hrms_tr.access.has_permission"}
doc_events = {
	"Leave Application": {
		"validate": "hrms_tr.leave.validate_approval",
		"before_cancel": "hrms_tr.leave.validate_cancellation",
	},
	"DocShare": {"validate": "hrms_tr.access.deny_sharing"},
	"User": {"before_save": "hrms_tr.users.keep_portal_user"},
}
extend_doctype_class = {
	"Leave Application": "hrms_tr.leave_application.LeaveApplication",
	"Report": "hrms_tr.hrms_endpoints.ReportAccess",
	"Prepared Report": "hrms_tr.hrms_endpoints.PreparedReportAccess",
	"Attendance Request": "hrms_tr.hrms_endpoints.AttendanceRequestAccess",
}

override_whitelisted_methods = {
	"hrms.hr.doctype.leave_application.leave_application.get_leave_details": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.api.get_leave_balance_map": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.api.get_leave_types": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.payroll.doctype.salary_slip.salary_slip.make_salary_slip_from_timesheet": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.payroll.doctype.salary_structure.salary_structure.make_salary_slip": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_events": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
}
