app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

fixtures = [{"dt": "Role", "filters": [["name", "=", "AI Manager"]]}]

auth_hooks = ["platform_core.model_gateway.agent_access.authenticate_request"]
