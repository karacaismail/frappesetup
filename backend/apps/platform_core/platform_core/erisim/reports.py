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


def reads_every_field(doctype: str, user: str) -> bool:
	"""Does the user hold read access at every permission level the document type uses?

	A query report returns whatever its SQL selects. Frappe does not remove fields by permission
	level there (`frappe/desk/query_report.py:980` only masks fields).
	"""
	meta = frappe.get_meta(doctype)
	fields = list(meta.fields)
	for table_field in meta.get_table_fields():
		fields += frappe.get_meta(table_field.options).fields
	used = {df.permlevel for df in fields if df.permlevel}
	return used <= set(meta.get_permlevel_access("read", user=user))


def denial(report_name: str | None, user: str | None = None) -> str | None:
	"""Return why the user may not get this report's data, or None when the report is allowed."""
	user = user or frappe.session.user
	if user == "Administrator" or not report_name:
		return None
	report = frappe.db.get_value(
		"Report", report_name, ["ref_doctype", "report_type", "reference_report"], as_dict=True
	)
	if not report:
		return None
	if report.reference_report:
		# A custom report uses the data of another report. That report decides.
		return denial(report.reference_report, user)
	if report.report_type == "Report Builder":
		# This report type reads through `frappe.get_list`, so the query hook and field levels apply.
		return None
	if report_name in (frappe.get_hooks(AWARE_REPORTS_HOOK) or []):
		return None
	if not reads_every_field(report.ref_doctype, user):
		return _("Report {0} cannot apply the field levels of {1}.").format(
			frappe.bold(report_name), frappe.bold(report.ref_doctype)
		)
	if rules.is_governed(report.ref_doctype) and not sees_every_record(report.ref_doctype, user):
		return _("Report {0} cannot apply the Access Rules of {1}.").format(
			frappe.bold(report_name), frappe.bold(report.ref_doctype)
		)
	return None


def guard(report_name: str | None, user: str | None = None) -> None:
	"""Raise a permission error when the report cannot honour the user's record and field limits."""
	reason = denial(report_name, user)
	if reason:
		frappe.throw(reason, frappe.PermissionError)


def guard_prepared_report(doc, method=None) -> None:
	"""“Prepared Report” kaydı açılmadan önce çalışır. Hazır rapor arka planda kapısız üretilir."""
	guard(doc.report_name)


def guard_auto_email_report(doc, method=None) -> None:
	"""“Auto Email Report” kaydı raporu `user` alanındaki kullanıcı adına çalıştırır."""
	guard(doc.report, doc.user)


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
