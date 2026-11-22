app_name = "cronhr"
app_title = "CronHR"
app_publisher = "CronHR"
app_description = "Leave application workflow"
app_email = "dev@example.test"
app_license = "gpl-3.0"

required_apps = ["hrms", "platform_core"]

before_install = "cronhr.setup.check_install"
before_migrate = "cronhr.setup.before_migrate"
after_migrate = "cronhr.setup.after_migrate"
before_uninstall = "cronhr.setup.before_uninstall"
after_uninstall = "cronhr.setup.after_uninstall"

ai_tools = ["cronhr.ai_tools.declarations"]
permission_query_conditions = {"Leave Application": "cronhr.access.query_condition"}
has_permission = {"Leave Application": "cronhr.access.has_permission"}
doc_events = {
	"Leave Application": {
		"validate": "cronhr.leave.validate_approval",
		"before_cancel": "cronhr.leave.validate_cancellation",
	},
	"DocShare": {"validate": "cronhr.access.deny_sharing"},
	"User": {"before_save": "cronhr.users.keep_portal_user"},
}
extend_doctype_class = {"Leave Application": "cronhr.leave_application.LeaveApplication"}

override_whitelisted_methods = {
	"hrms.hr.doctype.leave_application.leave_application.get_leave_details": "cronhr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on": "cronhr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.api.get_leave_balance_map": "cronhr.hrms_endpoints.deny_legacy_leave_query",
	"hrms.hr.doctype.leave_application.leave_application.get_events": "cronhr.hrms_endpoints.deny_legacy_leave_query",
}
