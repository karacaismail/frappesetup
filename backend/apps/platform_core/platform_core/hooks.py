app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Mobile sync tables must exist before the sequence row is created.
# The access rule engine switches off Auto Email Reports on governed data in the same two hooks.
after_install = [
	"platform_core.mobil.store.seed_sequence",
	"platform_core.erisim.reports.switch_off_governed_auto_email_reports",
]
after_migrate = [
	"platform_core.mobil.store.seed_sequence",
	"platform_core.erisim.reports.switch_off_governed_auto_email_reports",
]

fixtures = [{"dt": "Role", "filters": [["name", "=", "AI Manager"]]}]

# Access Rules change only through the engine's own AI tools, not the generic write tools (O-28).
ai_write_closed_doctypes = [
	"AI API",
	"AI Account",
	"Mobile Revoked Session",
	"Mobile Installation",
	"Mobile Account State",
	"Access Rule",
]

ai_tools = [
	"platform_core.model_gecidi.management_tools.declare",
	"platform_core.mobil.ai_tools.declarations",
	# AI tools of the access rule engine (D-9).
	"platform_core.erisim.ai_tools.declare",
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
		"on_trash": [
			"platform_core.kabuk.cache.invalidate_permissions",
			"platform_core.erisim.rules.clear_cache",
		],
		# The access rule engine forgets the rules it read in this request.
		"after_rename": ["platform_core.erisim.rules.clear_cache"],
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
		"on_trash": [
			"platform_core.kabuk.cache.invalidate_permissions",
			"platform_core.erisim.rules.clear_cache",
		],
		"after_rename": ["platform_core.erisim.rules.clear_cache"],
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
}

before_request = ["platform_core.kabuk.native_metadata.guard_website_rpc_before_request"]

# Keep a single list assignment. Credential hooks must precede the metadata guard when merged.
auth_hooks = ["platform_core.kabuk.native_metadata.guard_native_metadata"]

website_user_allowed_methods = [
	"platform_core.api.shell.get_bootstrap",
	"platform_core.api.meta.get_doctype",
	"frappe.auth.get_logged_user",
	"logout",
	"frappe.desk.search.search_link",
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
	# The user's own rule scopes. The explanation endpoint shows rule detail and is not listed.
	"platform_core.api.access.get_access_summary",
]

after_build = ["platform_core.kabuk.assets.remove_panel_source_maps"]

# Access rule engine (erisim-kurali task). Decision note: docs/kararlar/0006-erisim-kurali.md
permission_query_conditions = {"*": "platform_core.erisim.hooks.query_conditions"}
has_permission = {"*": "platform_core.erisim.hooks.has_permission"}
# On a document type with Access Rules every custom link search is refused. There is no allow-list.
override_whitelisted_methods = {
	"frappe.desk.search.search_link": "platform_core.erisim.link_search.search_link",
	"frappe.desk.search.search_widget": "platform_core.erisim.link_search.search_widget",
	# Link validation hands a search function from the request to the same search.
	"frappe.client.validate_link_and_fetch": "platform_core.erisim.link_search.validate_link_and_fetch",
}
# The report gate. Each extension class calls super(), so extensions of other apps keep running.
extend_doctype_class = {
	"Report": ["platform_core.erisim.reports.GuardedReport"],
	"Prepared Report": ["platform_core.erisim.reports.GuardedPreparedReport"],
	"Auto Email Report": ["platform_core.erisim.reports.GuardedAutoEmailReport"],
	"File": ["platform_core.erisim.reports.GuardedFile"],
}
# A Prepared Report queued before a rule existed is refused when its job starts.
before_job = ["platform_core.erisim.reports.refuse_prepared_report_job"]
