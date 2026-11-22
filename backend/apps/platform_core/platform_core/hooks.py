app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Erişim kuralı motoru (erisim-kurali işi). Karar notu: docs/kararlar/0006-erisim-kurali.md
permission_query_conditions = {"*": "platform_core.erisim.hooks.query_conditions"}
has_permission = {"*": "platform_core.erisim.hooks.has_permission"}
override_whitelisted_methods = {
	"frappe.desk.query_report.run": "platform_core.erisim.reports.run",
	"frappe.desk.query_report.export_query": "platform_core.erisim.reports.export_query",
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
	"Auto Email Report": {"validate": "platform_core.erisim.reports.guard_auto_email_report"},
}
