"""Saklama süresi dolan günlük ve öneri kayıtlarını silen, elle başlatılan komut.

Zamanlanmış iş yoktur (D-6). Komut şu üç yoldan başlar:

- `bench --site <site> execute platform_core.yapay_zeka.retention.purge --kwargs "{'older_than_days': 365}"`
- `platform_core.api.ai.purge_logs` ucu,
- yapay zekâ için `purge_action_log` aracı. Bu yol önizleme ve insan onayı ister.
"""

import frappe
from frappe import _

from platform_core.yapay_zeka import store

MIN_DAYS = 365


def purge(older_than_days: int = MIN_DAYS, dry_run: bool = False) -> dict:
	"""Eski kayıtları siler. `dry_run` doğruysa yalnız sayar (V-10).

	Sonucu bilinmeyen öneriler silinmez. İnsan onları önce kapatır.
	"""
	frappe.only_for("System Manager")
	days = int(older_than_days)
	if days < MIN_DAYS:
		frappe.throw(_("The retention period is at least {0} days.").format(MIN_DAYS), frappe.ValidationError)
	logs, proposals = store.purge_older_than(days, delete=not dry_run)
	return {"dry_run": bool(dry_run), "older_than_days": days, "logs": logs, "proposals": proposals}
