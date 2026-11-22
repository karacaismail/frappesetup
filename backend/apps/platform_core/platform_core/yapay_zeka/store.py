"""Katmanın kendi kayıtlarını yazan tek yer.

`ignore_permissions` ve doğrudan veritabanı okuması yalnız bu dosyadadır (G-4).
Gerekçe: “AI Action Log” ve “AI Action Proposal” sistem kayıtlarıdır. Son kullanıcının bu
türlere izni yoktur. Hedef kaydı kullanıcı seçmez. Kullanıcıya dönen satırlar burada
`user` alanıyla süzülür. Bir test bu istisnanın başka dosyaya taşmadığını denetler.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime

LOG = "AI Action Log"
PROPOSAL = "AI Action Proposal"


@contextmanager
def _as_system(doc: Document) -> Iterator[Document]:
	"""Write one of the layer's own records without the user's permission, for this write only.

	The flag stays on the document object otherwise and would skip later permission checks (G-4).
	It is put back in `finally`, also when the write fails.
	"""
	previous = doc.flags.ignore_permissions
	doc.flags.ignore_permissions = True  # nosemgrep: frappe-ignore-permissions
	try:
		yield doc
	finally:
		doc.flags.ignore_permissions = previous


def insert_log(values: dict) -> str:
	with _as_system(frappe.get_doc({"doctype": LOG, **values})) as doc:
		doc.insert()
	return doc.name


def insert_proposal(values: dict) -> Document:
	with _as_system(frappe.get_doc({"doctype": PROPOSAL, **values})) as doc:
		doc.insert()
	return doc


def load_proposal(name: str, *, for_update: bool = False) -> Document | None:
	if not isinstance(name, str) or not frappe.db.exists(PROPOSAL, name):
		return None
	return frappe.get_doc(PROPOSAL, name, for_update=for_update)


def save_proposal(doc: Document) -> None:
	with _as_system(doc):
		doc.save()


PROPOSAL_LIST_FIELDS = (
	"name",
	"creation",
	"status",
	"result",
	"tool",
	"target_doctype",
	"target_name",
	"destructive",
	"billable",
	"preview_json",
	"digest",
	"expires_at",
	"result_document",
	"error",
)


def proposals_of(user: str, status: str | None, start: int, limit: int) -> list[dict]:
	"""Return the user's proposals in one bounded query, newest first.

	A pending proposal past its time counts as expired, so the time is part of the query.
	"""
	filters: dict = {"user": user}
	or_filters = None
	now = now_datetime()
	if status == "pending":
		filters.update(status="pending", expires_at=(">=", now))
	elif status == "expired":
		filters["status"] = ("in", ("pending", "expired"))
		or_filters = [["status", "=", "expired"], ["expires_at", "<", now]]
	elif status:
		filters["status"] = status
	return frappe.get_all(
		PROPOSAL,
		filters=filters,
		or_filters=or_filters,
		fields=list(PROPOSAL_LIST_FIELDS),
		order_by="creation desc, name desc",
		limit_start=start,
		limit=limit,
	)


def unresolved_unknown_exists(target_key: str, *, exclude: str | None = None) -> bool:
	"""Aynı hedefte sonucu bilinmeyen bir yürütme var mı?"""
	filters = {"target_key": target_key, "status": "consumed", "result": "unknown"}
	if exclude:
		filters["name"] = ("!=", exclude)
	return bool(frappe.db.exists(PROPOSAL, filters))


def lock_target(target_key: str) -> list[dict]:
	"""Aynı hedefin bütün önerilerini satır kilidiyle okur.

	İki onay aynı hedefte yarışırsa ikincisi burada bekler. Birincinin `unknown` yazısı
	kesinleşince ikinci onu görür. Kilit veritabanındadır, birden çok sunucuda da çalışır.
	"""
	return frappe.db.get_values(
		PROPOSAL, {"target_key": target_key}, ["name", "status", "result"], for_update=True, as_dict=True
	)


def lock_row(doctype: str, name: str) -> bool:
	"""Bir sistem kaydının satırını kilitler. Satır yoksa yanlış döner.

	Yönetim araçları asıl hedefi yazmadan hemen önce bununla kilitler. Değer okunmaz.
	"""
	return bool(frappe.db.get_value(doctype, name, "name", for_update=True))


def latest_version(doctype: str | None, name: str | None) -> str | None:
	"""Yazmanın ürettiği “Version” kaydının adı. Yalnız günlüğe bağ olarak yazılır."""
	if not doctype or not name:
		return None
	return frappe.db.get_value(
		"Version", {"ref_doctype": doctype, "docname": name}, "name", order_by="creation desc"
	)


def purge_older_than(days: int, *, delete: bool) -> tuple[int, int]:
	"""Saklama süresi dolan kayıtları sayar, istenirse siler.

	Silme doğrudan veritabanında yapılır. Günlüğün controller'ı tek tek silmeyi engeller.
	Bu yolu yalnız `retention.purge` çağırır. O işlev yönetici rolünü denetler.
	"""
	cutoff = add_days(now_datetime(), -days)
	log_filters = {"creation": ("<", cutoff)}
	proposal_filters = {"creation": ("<", cutoff)}
	unresolved = frappe.get_all(PROPOSAL, filters={"status": "consumed", "result": "unknown"}, pluck="name")
	if unresolved:
		proposal_filters["name"] = ("not in", unresolved)
	counts = frappe.db.count(LOG, log_filters), frappe.db.count(PROPOSAL, proposal_filters)
	if delete:
		frappe.db.delete(LOG, log_filters)
		frappe.db.delete(PROPOSAL, proposal_filters)
	return counts
