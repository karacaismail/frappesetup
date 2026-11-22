app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"
# Shell permission generations. Keep other modules' hook entries alongside these.
clear_cache = ["platform_core.kabuk.cache.clear_cache"]

doc_events = {
	"User": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"Role": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"Role Profile": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"User Permission": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"Custom DocPerm": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"DocType": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"Custom Field": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	"Property Setter": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
	# This DocType is installed with the access-rule module. Keep shell validators fresh after rule changes.
	"Access Rule": {
		"on_update": "platform_core.kabuk.cache.invalidate_permissions",
		"on_trash": "platform_core.kabuk.cache.invalidate_permissions",
	},
}

# Keep a single list assignment. Credential hooks must precede the metadata guard when merged.
auth_hooks = ["platform_core.kabuk.native_metadata.guard_native_metadata"]

after_build = ["platform_core.kabuk.assets.remove_panel_source_maps"]
