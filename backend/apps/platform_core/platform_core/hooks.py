app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# --- platform-core-yz: AI access layer ---
auth_hooks = ["platform_core.yapay_zeka.agent_token.authenticate_request"]
after_install = "platform_core.yapay_zeka.setup.disable_builtin_mcp"
after_migrate = ["platform_core.yapay_zeka.setup.disable_builtin_mcp"]
