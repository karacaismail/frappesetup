"""Aracı belirteci: ajan servisinin kullanıcı adına kullandığı kısa ömürlü anahtar (G-148).

Belirteç rastgele bir değerdir. Sunucu yalnız SHA-256 özetini saklar. Kayıt önbellekte
süreli durur ve kendiliğinden silinir. Zamanlanmış temizlik yoktur (D-6).
"""

import hashlib
import secrets

import frappe
from frappe import _

from platform_core.yapay_zeka import access

PREFIX = "fsat_"
TTL_SECONDS = 300
MAX_CALLS = 20
MCP_PATH = "/api/method/platform_core.api.ai.mcp"
DEFAULT_AUDIENCE = "agent-service"


def _key(token: str, suffix: str = "") -> str:
	return "yz_agent_token:" + hashlib.sha256(token.encode()).hexdigest() + suffix


def issue() -> dict:
	"""İnsan oturumundan yeni belirteç üretir. Belirteç yalnız bu yanıtta görünür."""
	access.require_human("auth", tool="issue_agent_token")
	token = PREFIX + secrets.token_urlsafe(32)
	audience = frappe.conf.get("ai_agent_audience") or DEFAULT_AUDIENCE
	record = {"user": frappe.session.user, "sid": frappe.session.sid, "audience": audience}
	frappe.cache.set_value(_key(token), record, expires_in_sec=TTL_SECONDS)
	frappe.cache.set(frappe.cache.make_key(_key(token, ":calls")), MAX_CALLS, ex=TTL_SECONDS)
	return {"token": token, "expires_in": TTL_SECONDS, "max_calls": MAX_CALLS, "audience": audience}


def _bearer() -> str | None:
	scheme, _separator, token = (frappe.get_request_header("Authorization") or "").partition(" ")
	if scheme.lower() == "bearer" and token.startswith(PREFIX):
		return token
	return None


def _session_alive(sid: str) -> bool:
	"""Belirteci alan Frappe oturumu hâlâ açık mı? Frappe oturumları bu tabloda tutar."""
	sessions = frappe.qb.DocType("Sessions")
	return bool(frappe.qb.from_(sessions).select(sessions.sid).where(sessions.sid == sid).limit(1).run())


def authenticate_request() -> None:
	"""`auth_hooks` kancası. Geçerli belirteci yalnız MCP ucunda kullanıcıya çevirir.

	Kullanıcı ayarlanmazsa Frappe isteği 401 ile reddeder (`frappe/auth.py`).
	"""
	token = _bearer()
	if not token:
		return
	record = frappe.cache.get_value(_key(token), use_local_cache=False)
	if not record:
		return
	if frappe.request.path != MCP_PATH:
		_log_denied(record, "token_out_of_scope")
		return
	if frappe.request.cookies.get("sid"):
		raise frappe.PermissionError(_("Send either a session cookie or an agent token, not both."))
	if not _session_alive(record["sid"]):
		frappe.cache.delete_value(_key(token))
		return
	frappe.set_user(record["user"])
	frappe.local.yz_agent = {"token": token, **record}


def spend_call() -> bool:
	"""Belirtecin çağrı hakkından bir tane düşer. Hak bittiyse yanlış döner."""
	agent = getattr(frappe.local, "yz_agent", None)
	if not agent:
		return True
	return int(frappe.cache.decr(frappe.cache.make_key(_key(agent["token"], ":calls")))) >= 0


def _log_denied(record: dict, reason: str) -> None:
	access.record(
		"auth", decision="denied", deny_reason=reason, user=record["user"], principal_type=access.AGENT
	)
	# İstek 401 ile biter ve işlem geri alınır. Ret kaydı için burada kesinleştirilir.
	# Kanca isteğin başında çalışır, bu yüzden başka yazı yoktur.
	frappe.db.commit()  # nosemgrep
