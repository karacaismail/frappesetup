app_name = "cronhr"
app_title = "CronHR"
app_publisher = "CronHR"
app_description = "Leave application workflow"
app_email = "dev@example.test"
app_license = "gpl-3.0"

required_apps = ["hrms", "platform_core"]

before_install = "cronhr.setup.require_access_engine"
before_migrate = "cronhr.setup.require_access_engine"

ai_tools = ["cronhr.ai_tools.declarations"]
doc_events = {"Leave Application": {"validate": "cronhr.leave.validate_approval"}}
