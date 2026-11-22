app_name = "cronhr"
app_title = "CronHR"
app_publisher = "CronHR"
app_description = "Leave application workflow"
app_email = "dev@example.test"
app_license = "gpl-3.0"

required_apps = ["hrms", "platform_core"]

before_install = "cronhr.setup.check_install"
before_migrate = "cronhr.setup.require_access_engine"

ai_tools = ["cronhr.ai_tools.declarations"]
permission_query_conditions = {"Leave Application": "cronhr.access.query_condition"}
has_permission = {"Leave Application": "cronhr.access.has_permission"}
doc_events = {
	"Leave Application": {"validate": "cronhr.leave.validate_approval"},
	"DocShare": {"validate": "cronhr.access.deny_sharing"},
}
extend_doctype_class = {"Leave Application": "cronhr.leave_application.LeaveApplication"}
