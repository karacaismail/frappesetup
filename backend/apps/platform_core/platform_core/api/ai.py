"""Yapay zekâ erişim katmanının uçları. İş kuralı `platform_core.yapay_zeka` modülündedir.

Sözleşme: contracts/platform_core-yapay-zeka.openapi.yaml
"""

import frappe
from werkzeug.wrappers import Response

from platform_core.yapay_zeka import access, agent_token, proposals, retention
from platform_core.yapay_zeka import mcp as mcp_endpoint


@frappe.whitelist(methods=["POST"])
def mcp() -> Response:
	"""MCP ucu. İnsan oturumu ya da aracı belirteci ister."""
	return mcp_endpoint.handle()


@frappe.whitelist(methods=["POST"])
def issue_agent_token() -> dict:
	"""İnsan oturumundan kısa ömürlü aracı belirteci üretir."""
	return agent_token.issue()


@frappe.whitelist(methods=["GET"])
def list_proposals(status: str | None = None, limit: int = 20) -> list[dict]:
	"""Oturumdaki kullanıcının yazma önerilerini listeler."""
	return proposals.list_for_human(status, limit)


@frappe.whitelist(methods=["GET"])
def get_proposal(proposal_id: str) -> dict:
	"""Bir önerinin önizlemesini, özetini ve durumunu döner."""
	return proposals.read_for_human(proposal_id)


@frappe.whitelist(methods=["POST"])
def approve_proposal(proposal_id: str, digest: str) -> dict:
	"""Öneriyi onaylar ve işi bu istekte yürütür. Yıkıcı olabilir."""
	return proposals.approve(proposal_id, digest)


@frappe.whitelist(methods=["POST"])
def reject_proposal(proposal_id: str) -> dict:
	"""Bekleyen öneriyi reddeder."""
	return proposals.reject(proposal_id)


@frappe.whitelist(methods=["POST"])
def resolve_proposal(proposal_id: str, outcome: str) -> dict:
	"""Sonucu bilinmeyen öneriyi insan kararıyla kapatır."""
	return proposals.resolve(proposal_id, outcome)


@frappe.whitelist(methods=["POST"])
def purge_logs(older_than_days: int = retention.MIN_DAYS, dry_run: bool = True) -> dict:
	"""Saklama süresi dolan günlük ve öneri kayıtlarını siler. Yıkıcıdır. Varsayılan yalnız sayar."""
	return access.human_call("call", "purge_logs", lambda: retention.purge(older_than_days, dry_run=dry_run))
