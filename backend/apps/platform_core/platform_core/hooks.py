app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Mobile sync tables must exist before the sequence row is created.
# The AI access layer turns off Frappe's built-in MCP endpoint.
after_install = [
	"platform_core.mobil.store.seed_sequence",
	"platform_core.yapay_zeka.setup.disable_builtin_mcp",
]
after_migrate = [
	"platform_core.mobil.store.seed_sequence",
	"platform_core.yapay_zeka.setup.disable_builtin_mcp",
]

fixtures = [{"dt": "Role", "filters": [["name", "=", "AI Manager"]]}]

ai_write_closed_doctypes = [
	"AI API",
	"AI Account",
	"Mobile Revoked Session",
	"Mobile Installation",
	"Mobile Account State",
]

ai_tools = [
	"platform_core.model_gecidi.management_tools.declare",
	"platform_core.mobil.ai_tools.declarations",
]

# Shell permission generations. Keep other modules' hook entries alongside these.
clear_cache = ["platform_core.kabuk.cache.clear_cache"]

doc_events = {
	"User": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": [
			"platform_core.kabuk.cache.invalidate_permissions",
			"platform_core.mobil.store.delete_user_state",
		],
	},
	"Role": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Role Profile": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"User Permission": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom DocPerm": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"DocType": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Field": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Property Setter": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	# This DocType is installed with the access-rule module. Keep shell validators fresh after rule changes.
	"Access Rule": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"DocShare": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Role": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Workspace": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Workspace": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Sidebar": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Sidebar": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Page": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Report": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Dashboard": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Dashboard Chart": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Number Card": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Module Onboarding": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Module Def": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"System Settings": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Domain Settings": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Translation": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
}

before_request = ["platform_core.kabuk.native_metadata.guard_website_rpc_before_request"]
after_request = ["platform_core.kabuk.headers.add_security_headers"]

# Keep a single list assignment. Credential hooks must precede the metadata guard when merged.
auth_hooks = [
	"platform_core.yapay_zeka.agent_token.authenticate_request",
	"platform_core.kabuk.native_metadata.guard_native_metadata",
]

website_user_allowed_methods = [
	"platform_core.api.shell.get_bootstrap",
	"platform_core.api.meta.get_doctype",
	"frappe.auth.get_logged_user",
	"logout",
	"frappe.desk.search.search_link",
	# AI access layer: an end user talks to the layer and decides on their own proposals.
	# `purge_logs` is for the System Manager role and stays off this list.
	"platform_core.api.ai.mcp",
	"platform_core.api.ai.issue_agent_token",
	"platform_core.api.ai.list_proposals",
	"platform_core.api.ai.get_proposal",
	"platform_core.api.ai.approve_proposal",
	"platform_core.api.ai.reject_proposal",
	"platform_core.api.ai.resolve_proposal",
	"platform_core.api.mobile.v1_activity",
	"platform_core.api.mobile.v1_list_installations",
	"platform_core.api.mobile.v1_pull",
	"platform_core.api.mobile.v1_push",
	"platform_core.api.mobile.v1_register",
	"platform_core.api.mobile.v1_revoke",
	"platform_core.api.mobile.v1_revoke_installation",
	"platform_core.api.mobile_pwa.v1_activity",
	"platform_core.api.mobile_pwa.v1_list_installations",
	"platform_core.api.mobile_pwa.v1_pull",
	"platform_core.api.mobile_pwa.v1_push",
	"platform_core.api.mobile_pwa.v1_register",
	"platform_core.api.mobile_pwa.v1_revoke",
	"platform_core.api.mobile_pwa.v1_revoke_installation",
]

after_build = ["platform_core.kabuk.assets.remove_panel_source_maps"]
