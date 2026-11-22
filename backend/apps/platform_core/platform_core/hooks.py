app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Mobile sync tables must exist before the sequence row is created.
after_install = ["platform_core.mobil.store.seed_sequence"]
after_migrate = ["platform_core.mobil.store.seed_sequence"]

doc_events = {"User": {"on_trash": ["platform_core.mobil.store.delete_user_state"]}}

ai_tools = ["platform_core.mobil.ai_tools.declarations"]

ai_write_closed_doctypes = ["Mobile Revoked Session", "Mobile Installation", "Mobile Account State"]


website_user_allowed_methods = [
	"platform_core.api.mobile_pwa.v1_activity",
	"platform_core.api.mobile_pwa.v1_list_installations",
	"platform_core.api.mobile_pwa.v1_pull",
	"platform_core.api.mobile_pwa.v1_push",
	"platform_core.api.mobile_pwa.v1_register",
	"platform_core.api.mobile_pwa.v1_revoke",
	"platform_core.api.mobile_pwa.v1_revoke_installation",
]
