"""Sorgu raporu kapısı.

Sorgu raporu veriyi kendi SQL'iyle okur ve liste kancasından geçmez
(`frappe/desk/query_report.py:968`). Kapı, kayıtları daraltılmış kullanıcıyı reddeder.
`hooks.py` bu işlevleri `override_whitelisted_methods` ile Frappe'nin uçlarının yerine koyar.
Karar notu 9. bölüm.
"""

import frappe
from frappe import _
from frappe.desk import query_report

from platform_core.erisim import rules

AWARE_REPORTS_HOOK = "access_rule_aware_reports"


def sees_every_record(doctype: str, user: str) -> bool:
	"""Kullanıcının süzgeçsiz ve `all` kapsamlı bir okuma kuralı var mı?"""
	return any(
		rule["scope"] == "all" and not rule["filters"] for rule in rules.applicable(doctype, user, "read")
	)


def guard(report_name: str | None, user: str | None = None) -> None:
	"""Rapor kuralı uygulayamıyorsa ve kullanıcı daraltılmışsa izin hatası verir."""
	user = user or frappe.session.user
	if user == "Administrator" or not report_name:
		return
	report = frappe.db.get_value(
		"Report", report_name, ["ref_doctype", "report_type", "reference_report"], as_dict=True
	)
	if not report:
		return
	if report.reference_report:
		# Özel rapor başka raporun verisini kullanır. Karar asıl rapora göre verilir.
		return guard(report.reference_report, user)
	if report.report_type == "Report Builder":
		# Bu rapor türü veriyi `frappe.get_list` ile okur. Liste kancası çalışır.
		return
	if not rules.is_governed(report.ref_doctype):
		return
	if report_name in (frappe.get_hooks(AWARE_REPORTS_HOOK) or []):
		return
	if sees_every_record(report.ref_doctype, user):
		return
	frappe.throw(
		_("Report {0} cannot apply the Access Rules of {1}.").format(
			frappe.bold(report_name), frappe.bold(report.ref_doctype)
		),
		frappe.PermissionError,
	)


@frappe.whitelist(methods=["GET", "POST"])
@frappe.read_only()
def run(
	report_name: str,
	filters: str | dict | None = None,
	user: str | None = None,
	ignore_prepared_report: bool = False,
	custom_columns: str | list | None = None,
	is_tree: bool = False,
	parent_field: str | None = None,
	are_default_filters: bool = True,
	js_filters: str | list | None = None,
) -> dict:
	"""`frappe.desk.query_report.run` ucunun kapılı hali. Girdiler aynıdır."""
	if not frappe.has_permission(frappe.db.get_value("Report", report_name, "ref_doctype"), "report"):
		frappe.throw(_("No permission to run report {0}.").format(report_name), frappe.PermissionError)
	guard(report_name)
	return query_report.run(
		report_name=report_name,
		filters=filters,
		ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns,
		is_tree=is_tree,
		parent_field=parent_field,
		are_default_filters=are_default_filters,
		js_filters=js_filters,
	)


@frappe.whitelist(methods=["GET", "POST"])
def export_query():
	"""`frappe.desk.query_report.export_query` ucunun kapılı hali."""
	report_name = frappe.form_dict.get("report_name")
	if not frappe.has_permission(frappe.db.get_value("Report", report_name, "ref_doctype"), "report"):
		frappe.throw(_("No permission to export report {0}.").format(report_name), frappe.PermissionError)
	guard(report_name)
	return query_report.export_query()
