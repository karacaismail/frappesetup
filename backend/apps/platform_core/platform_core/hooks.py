app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Erişim kuralı motoru (erisim-kurali işi). Karar notu: docs/kararlar/0006-erisim-kurali.md
permission_query_conditions = {"*": "platform_core.erisim.hooks.query_conditions"}
has_permission = {"*": "platform_core.erisim.hooks.has_permission"}
# Custom link searches are filtered by the engine.
override_whitelisted_methods = {
	"frappe.desk.search.search_link": "platform_core.erisim.link_search.search_link",
	"frappe.desk.search.search_widget": "platform_core.erisim.link_search.search_widget",
}
# The report gate, the Auto Email Report refusal and the prepared report file check.
extend_doctype_class = {
	"Report": ["platform_core.erisim.reports.GuardedReport"],
	"Auto Email Report": ["platform_core.erisim.reports.GuardedAutoEmailReport"],
	"File": ["platform_core.erisim.reports.GuardedFile"],
}
doc_events = {
	"Role": {
		"after_rename": "platform_core.erisim.rules.clear_cache",
		"on_trash": "platform_core.erisim.rules.clear_cache",
	},
	"DocType": {
		"after_rename": "platform_core.erisim.rules.clear_cache",
		"on_trash": "platform_core.erisim.rules.clear_cache",
	},
	"Prepared Report": {"before_insert": "platform_core.erisim.reports.guard_prepared_report"},
}
