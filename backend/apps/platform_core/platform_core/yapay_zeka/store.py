"""Katmanın kendi kayıtlarını yazan tek yer.

`ignore_permissions` ve doğrudan veritabanı okuması yalnız bu dosyadadır (G-4).
Gerekçe: “AI Action Log” ve “AI Action Proposal” sistem kayıtlarıdır. Son kullanıcının bu
türlere izni yoktur. Hedef kaydı kullanıcı seçmez. Kullanıcıya dönen satırlar burada
`user` alanıyla süzülür. Bir test bu istisnanın başka dosyaya taşmadığını denetler.
"""

import frappe
from frappe.model.document import Document

LOG = "AI Action Log"
PROPOSAL = "AI Action Proposal"


def insert_log(values: dict) -> str:
	return frappe.get_doc({"doctype": LOG, **values}).insert(ignore_permissions=True).name


def insert_proposal(values: dict) -> Document:
	return frappe.get_doc({"doctype": PROPOSAL, **values}).insert(ignore_permissions=True)


def load_proposal(name: str, *, for_update: bool = False) -> Document | None:
	if not isinstance(name, str) or not frappe.db.exists(PROPOSAL, name):
		return None
	return frappe.get_doc(PROPOSAL, name, for_update=for_update)


def save_proposal(doc: Document) -> None:
	doc.save(ignore_permissions=True)


def proposals_of(user: str, status: str | None, limit: int) -> list[str]:
	filters = {"user": user}
	if status:
		filters["status"] = status
	return frappe.get_all(PROPOSAL, filters=filters, pluck="name", order_by="creation desc", limit=limit)


def unresolved_unknown_exists(target_key: str, *, exclude: str | None = None) -> bool:
	"""Aynı hedefte sonucu bilinmeyen bir yürütme var mı?"""
	filters = {"target_key": target_key, "status": "consumed", "result": "unknown"}
	if exclude:
		filters["name"] = ("!=", exclude)
	return bool(frappe.db.exists(PROPOSAL, filters))


def latest_version(doctype: str | None, name: str | None) -> str | None:
	"""Yazmanın ürettiği “Version” kaydının adı. Yalnız günlüğe bağ olarak yazılır."""
	if not doctype or not name:
		return None
	return frappe.db.get_value(
		"Version", {"ref_doctype": doctype, "docname": name}, "name", order_by="creation desc"
	)
