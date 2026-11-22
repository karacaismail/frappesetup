"""Frappe'nin izin kancalarına bağlanan işlevler.

`hooks.py` dosyası bu işlevleri `"*"` anahtarıyla bütün kayıt türlerine bağlar.
Frappe 16'da `has_permission` kancası `None` dönerse erişim reddedilir
(`frappe/permissions.py:497`). Bu yüzden işlev her zaman `True` ya da `False` döner.
"""

import frappe

from platform_core.erisim import engine, reports, rules


def has_permission(doc, ptype: str | None = None, user: str | None = None, debug: bool = False) -> bool:
	"""Tek kayıt kancası. Motor yalnız daraltır: `True` izin vermez, rol izni ayrıca aranır."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if doc.doctype == reports.PREPARED_REPORT:
		# A stored report result is as sensitive as running the report now.
		return not reports.denial(doc.report_name, user)
	if doc.doctype == "File" and doc.get("attached_to_doctype") == reports.PREPARED_REPORT:
		return not reports.prepared_report_denial(doc.get("attached_to_name"), user)
	if not rules.is_governed(doc.doctype):
		return True
	return engine.decide(doc, ptype, user)


def query_conditions(user: str | None = None, doctype: str | None = None):
	"""Liste kancası. Kurallı olmayan türde koşul eklemez."""
	user = user or frappe.session.user
	if user == "Administrator" or not doctype:
		return None
	return engine.list_criterion(doctype, user)
