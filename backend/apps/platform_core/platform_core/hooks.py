app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Identity: Keycloak sign-in, service tokens and the local sign-in gate (identity/README.md).
# Other tasks append to the same list keys; do not replace them.
before_login = ["platform_core.identity.login_policy.before_login"]
before_request = [
	"platform_core.identity.login_policy.before_request",
	"platform_core.identity.session_policy.before_request",
	"platform_core.shell.native_metadata.guard_website_rpc_before_request",
]
on_session_creation = ["platform_core.identity.session_policy.on_session_creation"]
# Keep the idle clock across site cache clears. Frappe matches prefixes.
persistent_cache_keys = ["kimlik_activity:"]
# Keep a single list assignment. Credential hooks must precede the metadata guard (platform-core-kabuk).
auth_hooks = [
	"platform_core.identity.service_token.validate",
	"platform_core.ai.agent_token.authenticate_request",
	"platform_core.ai.oauth.authenticate_request",
	"platform_core.shell.native_metadata.guard_native_metadata",
]
# AU-19: local sign-in functions are replaced by gated wrappers (identity/login_policy.py).
override_whitelisted_methods = {
	"frappe.core.doctype.user.user.reset_password": "platform_core.identity.login_policy.reset_password",
	"frappe.core.doctype.user.user.update_password": "platform_core.identity.login_policy.update_password",
	"frappe.core.doctype.user.user.sign_up": "platform_core.identity.login_policy.sign_up",
	"frappe.www.login.send_login_link": "platform_core.identity.login_policy.send_login_link",
	"frappe.www.login.login_via_key": "platform_core.identity.login_policy.login_via_key",
	"frappe.www.login.login_via_token": "platform_core.identity.login_policy.login_via_token",
	"frappe.integrations.oauth2_logins.login_via_google": "platform_core.identity.login_policy.login_via_google",
	"frappe.integrations.oauth2_logins.login_via_github": "platform_core.identity.login_policy.login_via_github",
	"frappe.integrations.oauth2_logins.login_via_facebook": "platform_core.identity.login_policy.login_via_facebook",
	"frappe.integrations.oauth2_logins.login_via_frappe": "platform_core.identity.login_policy.login_via_frappe",
	"frappe.integrations.oauth2_logins.login_via_office365": "platform_core.identity.login_policy.login_via_office365",
	"frappe.integrations.oauth2_logins.login_via_salesforce": "platform_core.identity.login_policy.login_via_salesforce",
	"frappe.integrations.oauth2_logins.login_via_fairlogin": "platform_core.identity.login_policy.login_via_fairlogin",
	"frappe.integrations.oauth2_logins.login_via_keycloak": "platform_core.identity.login_policy.login_via_keycloak",
	"frappe.integrations.oauth2_logins.custom": "platform_core.identity.login_policy.custom",
	"frappe.integrations.doctype.ldap_settings.ldap_settings.login": "platform_core.identity.login_policy.ldap_login",
	# Access rule engine: on a document type with Access Rules every custom link search is refused.
	# There is no allow-list.
	"frappe.desk.search.search_link": "platform_core.access.link_search.search_link",
	"frappe.desk.search.search_widget": "platform_core.access.link_search.search_widget",
	# Link validation hands a search function from the request to the same search.
	"frappe.client.validate_link_and_fetch": "platform_core.access.link_search.validate_link_and_fetch",
}

# Identity: Frappe idle timeout of 1 hour (O-25, identity/session_policy.py).
# Mobile sync tables must exist before the sequence row is created.
# The access rule engine switches off Auto Email Reports on governed data in the same two hooks.
# The AI access layer turns off Frappe's built-in MCP endpoint.
after_install = [
	"platform_core.identity.session_policy.apply",
	"platform_core.mobile.store.seed_sequence",
	"platform_core.access.reports.switch_off_governed_auto_email_reports",
	"platform_core.ai.setup.disable_builtin_mcp",
]
after_migrate = [
	"platform_core.identity.session_policy.apply",
	"platform_core.mobile.store.seed_sequence",
	"platform_core.access.reports.switch_off_governed_auto_email_reports",
	"platform_core.ai.setup.disable_builtin_mcp",
]

fixtures = [{"dt": "Role", "filters": [["name", "=", "PLT AI Manager"]]}]

# Access Rules change only through the engine's own AI tools, not the generic write tools (O-28).
# O-28: the identity link changes only through the identity endpoints, never through generic AI writes.
ai_write_closed_doctypes = [
	"PLT Identity Link",
	"Platform Identity Deletion",
	"PLT AI API",
	"PLT AI Account",
	"PLT Mobile Revoked Session",
	"PLT Mobile Installation",
	"PLT Mobile Account State",
	"PLT Access Rule",
	"PLT Record Link",
	"PLT Record Access Request",
]
# Website User method allow list (docs/sozlesmeler.md). Identity adds only the method a portal user calls.
website_user_allowed_methods = [
	"platform_core.api.auth.logout",
	"platform_core.api.auth.get_csrf_token",
	"platform_core.api.shell.get_bootstrap",
	"platform_core.api.shell.record_preview_image",
	"platform_core.api.access.create_record_link",
	"platform_core.api.access.open_record_link",
	"platform_core.api.access.revoke_record_link",
	"platform_core.api.access.request_record_access",
	"platform_core.api.collection.group_summary",
	"platform_core.api.meta.get_doctype",
	"frappe.auth.get_logged_user",
	"logout",
	"frappe.desk.search.search_link",
	# AI access layer: an end user talks to the layer and decides on their own proposals.
	# `purge_logs` is for the System Manager role and stays off this list.
	"platform_core.api.ai.mcp",
	"platform_core.api.ai.mcp_resource_metadata",
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
	# The user's own rule scopes. The explanation endpoint shows rule detail and is not listed.
	"platform_core.api.access.get_access_summary",
]


ai_tools = [
	"platform_core.model_gateway.management_tools.declare",
	"platform_core.mobile.ai_tools.declarations",
	# AI tools of the access rule engine (D-9).
	"platform_core.access.ai_tools.declare",
]

# Shell permission generations. Keep other modules' hook entries alongside these.
clear_cache = ["platform_core.shell.cache.clear_cache"]

doc_events = {
	"User": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": [
			"platform_core.shell.cache.invalidate_permissions",
			"platform_core.mobile.store.delete_user_state",
		],
	},
	"Role": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": [
			"platform_core.shell.cache.invalidate_permissions",
			"platform_core.access.rules.clear_cache",
		],
		# The access rule engine forgets the rules it read in this request.
		"after_rename": ["platform_core.access.rules.clear_cache"],
	},
	"Role Profile": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"User Permission": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Custom DocPerm": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"DocType": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": [
			"platform_core.shell.cache.invalidate_permissions",
			"platform_core.access.rules.clear_cache",
		],
		"after_rename": ["platform_core.access.rules.clear_cache"],
	},
	"Custom Field": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Property Setter": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	# This DocType is installed with the access-rule module. Keep shell validators fresh after rule changes.
	"PLT Access Rule": {
		"on_update": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"DocShare": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Custom Role": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Workspace": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Custom Workspace": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Sidebar": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Custom Sidebar": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Page": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Report": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Dashboard": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Dashboard Chart": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Number Card": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Module Onboarding": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Module Def": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"System Settings": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Domain Settings": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
	},
	"Translation": {
		"on_change": ["platform_core.shell.cache.invalidate_permissions"],
		"on_trash": ["platform_core.shell.cache.invalidate_permissions"],
	},
}

after_request = ["platform_core.shell.headers.add_security_headers"]

# Panel client routes (platform-core-kabuk): every /panel/<path> renders the /panel page.
website_route_rules = [{"from_route": "/panel/<path:app_path>", "to_route": "panel"}]

after_build = ["platform_core.shell.assets.remove_panel_source_maps"]

# Access rule engine (erisim-kurali task). Decision note: docs/decisions/0006-access-rule.md
permission_query_conditions = {"*": "platform_core.access.hooks.query_conditions"}
has_permission = {"*": "platform_core.access.hooks.has_permission"}
# The access rule engine's link search overrides are in override_whitelisted_methods above.
# The report gate. Each extension class calls super(), so extensions of other apps keep running.
extend_doctype_class = {
	"Report": ["platform_core.access.reports.GuardedReport"],
	"Prepared Report": ["platform_core.access.reports.GuardedPreparedReport"],
	"Auto Email Report": ["platform_core.access.reports.GuardedAutoEmailReport"],
	"File": ["platform_core.access.reports.GuardedFile"],
}
# A Prepared Report queued before a rule existed is refused when its job starts.
before_job = ["platform_core.access.reports.refuse_prepared_report_job"]
