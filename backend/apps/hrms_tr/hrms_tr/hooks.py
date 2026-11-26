app_name = "hrms_tr"
app_title = "HRMS TR"
app_publisher = "HRMS TR"
app_description = "Leave application workflow"
app_email = "dev@example.test"
app_license = "GPL-3.0-only"

required_apps = ["hrms", "platform_core"]

before_request = ["hrms_tr.users.require_tenant_portal"]
website_user_allowed_methods = [
	"hrms_tr.api.approve_leave",
	"hrms_tr.api.cancel_leave",
	"hrms_tr.api.get_leave_approver",
	"hrms_tr.api.get_leave_request_context",
]

before_install = "hrms_tr.setup.check_install"
before_migrate = "hrms_tr.setup.before_migrate"
# The Role Profiles are not fixtures: a profile write leaves a lock (AJA-934). The setup step opens
# only the missing ones. `after_sync` runs on install after the fixtures, so the roles exist.
after_sync = ["hrms_tr.role_profiles.ensure"]
after_migrate = ["hrms_tr.role_profiles.ensure", "hrms_tr.setup.after_migrate"]
before_uninstall = "hrms_tr.setup.before_uninstall"
after_uninstall = "hrms_tr.setup.after_uninstall"

ai_tools = ["hrms_tr.ai_tools.declarations"]
permission_query_conditions = {"Leave Application": "hrms_tr.access.query_condition"}
has_permission = {
	"Leave Application": "hrms_tr.access.has_permission",
	"File": "hrms_tr.employee_privacy.file_has_permission",
}
doc_events = {
	"Leave Application": {
		"autoname": "hrms_tr.leave.name_portal_leave",
		"before_validate": "hrms_tr.leave.validate_manager_fields",
		"before_update_after_submit": "hrms_tr.leave.validate_manager_fields",
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
	"File": "hrms_tr.hrms_endpoints.PreparedReportFileAccess",
	"Attendance Request": "hrms_tr.hrms_endpoints.AttendanceRequestAccess",
}

override_whitelisted_methods = {
	"hrms.www.hrms.get_context_for_dev": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_leave_details": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.api.get_leave_balance_map": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.api.get_leave_types": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.payroll.doctype.salary_slip.salary_slip.make_salary_slip_from_timesheet": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.payroll.doctype.salary_structure.salary_structure.make_salary_slip": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_events": "hrms_tr.hrms_endpoints.deny_legacy_leave_query",
}


user_data_fields = [
	{
		"doctype": "Employee",
		"filter_by": "user_id",
		"clear_fields": ["blood_group", "marital_status", "attendance_device_id"],
		"redact_fields": [
			"first_name",
			"middle_name",
			"last_name",
			"employee_name",
			"personal_email",
			"prefered_email",
			"cell_number",
			"date_of_birth",
			"company_email",
			"emergency_phone_number",
			"person_to_be_contacted",
			"relation",
			"passport_number",
			"date_of_issue",
			"valid_upto",
			"place_of_issue",
			"iban",
			"bank_name",
			"bank_ac_no",
			"health_details",
			"blood_group",
			"marital_status",
			"family_background",
			"current_address",
			"permanent_address",
			"bio",
			"image",
			"attendance_device_id",
			"health_insurance_no",
		],
	},
]
