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
# End users (Website User) talk to the layer and decide on their own proposals. `purge_logs` is
# for the System Manager role and stays off this list.
website_user_allowed_methods = [
	"platform_core.api.ai.mcp",
	"platform_core.api.ai.issue_agent_token",
	"platform_core.api.ai.list_proposals",
	"platform_core.api.ai.get_proposal",
	"platform_core.api.ai.approve_proposal",
	"platform_core.api.ai.reject_proposal",
	"platform_core.api.ai.resolve_proposal",
]
