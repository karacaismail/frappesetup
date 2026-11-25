"""Apply the tenant localization defaults required by G-41."""

import frappe
from frappe.core.doctype.system_settings.system_settings import clear_system_settings_cache
from frappe.translate import set_default_language

SYSTEM_SETTINGS = {
	"country": "Türkiye",
	"language": "tr",
	"time_zone": "Europe/Istanbul",
	"currency": "TRY",
	"number_format": "#.###,##",
	"date_format": "dd.mm.yyyy",
	"time_format": "HH:mm",
	"first_day_of_the_week": "Monday",
	"float_precision": "2",
	"currency_precision": "2",
	# Product decision, 24 November 2026: half values round up. Change it here only.
	"rounding_method": "Commercial Rounding",
}
# Accounts, Selling and Buying Settings keep the ERPNext defaults on purpose.


def apply(_wizard_args=None) -> None:
	"""Apply defaults after the wizard and after migrations."""
	if _update_settings("System Settings", SYSTEM_SETTINGS | _brand_settings()):
		clear_system_settings_cache()

	for key, value in SYSTEM_SETTINGS.items():
		if frappe.db.get_default(key) != value:
			frappe.db.set_default(key, value)
	if frappe.db.get_default("lang") != SYSTEM_SETTINGS["language"]:
		set_default_language(SYSTEM_SETTINGS["language"])

	if "erpnext" in frappe.get_installed_apps():
		currency = SYSTEM_SETTINGS["currency"]
		_update_settings(
			"Global Defaults", {"country": SYSTEM_SETTINGS["country"], "default_currency": currency}
		)
		if not frappe.db.get_value("Currency", currency, "enabled"):
			frappe.db.set_value("Currency", currency, "enabled", 1)


def _brand_settings() -> dict[str, str]:
	"""Show the tenant brand from the existing identity setting; never invent one."""
	brand = (frappe.conf.get("identity_brand_name") or "").strip()
	return {"app_name": brand} if brand else {}


def _update_settings(doctype: str, defaults: dict[str, str]) -> bool:
	settings = frappe.get_single(doctype)
	changes = {field: value for field, value in defaults.items() if settings.get(field) != value}
	if not changes:
		return False

	# A full save can rewrite unrelated security settings and ERPNext print property setters.
	frappe.db.set_single_value(doctype, changes)
	return True
