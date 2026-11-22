"""Aracı belirteci: ajan servisinin kullanıcı adına kullandığı kısa ömürlü anahtar (G-148).

Belirteç rastgele bir değerdir. Sunucu yalnız SHA-256 özetini saklar. Kayıt önbellekte
süreli durur ve kendiliğinden silinir. Zamanlanmış temizlik yoktur (D-6).
"""

import hashlib
import secrets
from datetime import UTC, datetime

import frappe
from frappe import _
from frappe.sessions import get_expired_threshold, get_expiry_in_seconds
from frappe.utils import now, time_diff_in_seconds

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
	access.record("auth", decision="allowed", tool="issue_agent_token")
	return {"token": token, "expires_in": TTL_SECONDS, "max_calls": MAX_CALLS, "audience": audience}


def _bearer() -> str | None:
	scheme, _separator, token = (frappe.get_request_header("Authorization") or "").partition(" ")
	if scheme.lower() == "bearer" and token.startswith(PREFIX):
		return token
	return None


def _session_alive(sid: str, user: str) -> bool:
	"""Belirteci alan Frappe oturumu hâlâ geçerli mi?

	Ölçütler Frappe'nin oturum okumasıyla aynıdır (`frappe/sessions.py` içinde
	`get_session_data_from_cache` ve `get_session_data_from_db`): hareketsizlik süresi,
	`session_end` zamanı ve veritabanındaki son kullanım. Satırın durması yetmez.
	"""
	cached = frappe.cache.hget("session", sid)
	if cached:
		data = cached.get("data") or {}
		idle = time_diff_in_seconds(now(), data.get("last_updated"))
		if idle > get_expiry_in_seconds(data.get("session_expiry")):
			return False
		session_end = data.get("session_end")
		if session_end and datetime.now(tz=UTC) > datetime.fromisoformat(session_end):
			return False
		return cached.get("user") == user
	sessions = frappe.qb.DocType("Sessions")
	rows = (
		frappe.qb.from_(sessions)
		.select(sessions.user)
		.where(sessions.sid == sid)
		.where(sessions.lastupdate > get_expired_threshold())
		.limit(1)
		.run()
	)
	return bool(rows) and rows[0][0] == user


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
	# Frappe, `cmd` alanı varsa yolu yok sayar ve o işlevi çalıştırır (`frappe/app.py`).
	# Bu yüzden `cmd` taşıyan istekte belirteç kimliğe çevrilmez.
	if frappe.request.path != MCP_PATH or "cmd" in frappe.form_dict or "cmd" in frappe.request.args:
		_log_denied(record, "token_out_of_scope")
		return
	if frappe.request.cookies.get("sid") not in (None, "", "Guest"):
		_log_denied(record, "cookie_with_token")
		raise frappe.PermissionError(_("Send either a session cookie or an agent token, not both."))
	if not _session_alive(record["sid"], record["user"]):
		_log_denied(record, "session_ended")
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
	"""Log a refusal of a known token. The hook runs before anything else in the request."""
	access.record_denial("auth", reason, user=record["user"], principal_type=access.AGENT)
