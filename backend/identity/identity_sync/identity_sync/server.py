"""Servisin HTTP uçları. Sözleşme `backend/contracts/identity_sync.openapi.yaml` dosyasındadır.

Sunucu Python'un kendi `http.server` modülüdür ve istekleri tek tek işler.

Kimlik kuralları şunlardır:

- Olay ucu imza ister. İmza zaman damgasını, yürütme seçimini ve gövdeyi kapsar.
- Öteki uçlar servis belirteci ister. Elle başlatılan her komutun burada bir ucu vardır.
- Yapay zekâ aracısı yalnız okur ve önizler. Yürütmeyi yalnız onay katmanı başlatır.
  Onay katmanı insan onayından sonra kendi servis belirteciyle çağırır.
- Yürütme isteği önizlemenin özetini taşır. Plan değiştiyse servis yürütmez.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import re
import socket
import sqlite3
import time
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from identity_sync.app import App
from identity_sync.auth import TokenRejected, Verifier
from identity_sync.events import RESOURCE_ID, EventError, from_keycloak, looks_like_keycloak, parse_event
from identity_sync.httpjson import HttpError, TransportError
from identity_sync.mapping import digest_of
from identity_sync.pipeline import PreviewChanged, replay_report

__all__ = ["TokenRejected", "make_server"]

MAX_BODY_BYTES = 65536
_MAX_DRAIN_BYTES = 1024 * 1024
SIGNATURE_HEADER = "X-Identity-Sync-Signature"
TIMESTAMP_HEADER = "X-Identity-Sync-Timestamp"
SIGNATURE_WINDOW_SECONDS = 300
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^[0-9]{1,12}$")
_LOG = logging.getLogger("identity_sync")

Reply = tuple[int, object]
Query = Mapping[str, list[str]]


class _BadRequest(Exception):
    pass


class _Forbidden(Exception):
    pass


class _DeadlineReader(io.RawIOBase):
    """Soketten okur ve isteğin toplam süresini sınırlar.

    Soketin kendi süre sınırı her okumada yeniden başlar. Yavaş yavaş veri gönderen
    istemci o sınırı hiç doldurmaz. Bu sınıf kalan süreyi her okumada yeniden hesaplar.
    """

    def __init__(self, connection: socket.socket, deadline: float) -> None:
        super().__init__()
        self._connection = connection
        self._deadline = deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("request deadline exceeded")
        self._connection.settimeout(remaining)
        return self._connection.recv_into(buffer)


def _json_object(body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _BadRequest from None
    if not isinstance(payload, dict):
        raise _BadRequest
    return payload


def _flag(payload: Mapping[str, object], name: str, *, default: bool | None = None) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise _BadRequest
    return value


def _text(payload: Mapping[str, object], name: str, *, required: bool = False, max_length: int = 150) -> str:
    value = payload.get(name, None if required else "")
    if not isinstance(value, str) or len(value) > max_length or (required and not value):
        raise _BadRequest
    return value


def _event_mode(query: Query) -> str:
    """Olay isteğinin kipini döner. Belirsiz `dry_run` değeri hiçbir zaman yürütmeye dönüşmez."""
    values = query.get("dry_run", ["false"])
    if values == ["true"]:
        return "preview"
    if values == ["false"]:
        return "execute"
    raise _BadRequest


class _Api:
    """Uçların iş kısmı. HTTP ayrıntısını bilmez."""

    def __init__(self, app: App) -> None:
        self._app = app
        self._settings = app.settings

    # --- olay ucu: imzalı, otomatik ---

    def post_event(self, body: bytes, mode: str) -> Reply:
        dry_run = mode == "preview"
        payload = _json_object(body)
        try:
            if looks_like_keycloak(payload):
                payload = from_keycloak(payload, realm_id=self._settings.realm_id, realm=self._settings.realm)
                if payload.get("type") == "ORGANIZATION_MEMBERSHIP_CREATE" and "user_id" not in payload:
                    # Keycloak üye ekleme olayında kullanıcıyı vermez. Servis bu olayı işleyemez.
                    _LOG.warning("ignored membership event without user")
                    return (200 if dry_run else 202), {"status": "ignored", "actions": []}
            event = parse_event(payload)
        except EventError:
            raise _BadRequest from None
        result = self._app.processor.handle(event, dry_run=dry_run)
        return (200 if dry_run else 202), result.to_dict()

    # --- okuma uçları ---

    def post_reconcile(self, _body: bytes, _azp: str) -> Reply:
        differences = [difference.to_dict() for difference in self._app.reconcile()]
        return 200, {"count": len(differences), "differences": differences}

    def get_dead_letters(self, _body: bytes, _azp: str) -> Reply:
        return 200, {"dead_letters": [letter.to_dict() for letter in self._app.store.dead_letters()]}

    # --- yazma uçları: önizleme herkese, yürütme yalnız onay katmanına ---

    def _approval(self, operation: str, payload: Mapping[str, object], azp: str) -> str:
        """Yürütme isteğini denetler ve onaylanan önizlemenin özetini döner.

        Yürütmeyi yalnız `execute_azp` listesindeki istemci başlatır. İstek onay kimliğini
        ve önizleme özetini taşır. Servis çağıranı, onayı ve özeti günlüğe yazar.
        """
        if azp not in self._settings.execute_azp:
            _LOG.warning("refused execute operation=%s azp=%s", operation, azp)
            raise _Forbidden
        digest = _text(payload, "preview_digest", required=True, max_length=64)
        approval_id = _text(payload, "approval_id", required=True, max_length=128)
        if not _DIGEST.fullmatch(digest) or not RESOURCE_ID.fullmatch(approval_id):
            raise _BadRequest
        _LOG.info("execute operation=%s azp=%s approval_id=%s preview_digest=%s", operation, azp, approval_id, digest)
        return digest

    def post_replay(self, body: bytes, azp: str) -> Reply:
        payload = _json_object(body)
        dry_run = _flag(payload, "dry_run")
        include_unknown = _flag(payload, "include_unknown", default=False)
        if dry_run:
            report = replay_report(self._app.processor.replay_dead_letters(dry_run=True, include_unknown=include_unknown))
            return 200, {"results": report, "preview_digest": digest_of(report)}
        digest = self._approval("replay_dead_letters", payload, azp)
        try:
            results = self._app.processor.replay_dead_letters(include_unknown=include_unknown, expected_digest=digest)
        except PreviewChanged:
            return 409, {"error": "preview_changed"}
        return 200, {"results": replay_report(results)}

    def post_invitation(self, body: bytes, azp: str) -> Reply:
        payload = _json_object(body)
        dry_run = _flag(payload, "dry_run")
        email = _text(payload, "email", required=True, max_length=254)
        organization_id = _text(payload, "organization_id", required=True)
        first_name, last_name = _text(payload, "first_name"), _text(payload, "last_name")
        if not _EMAIL.fullmatch(email) or not RESOURCE_ID.fullmatch(organization_id):
            raise _BadRequest
        digest = None if dry_run else self._approval("invite_user", payload, azp)
        keycloak = self._app.keycloak
        preview = keycloak.invite_user(email, first_name, last_name, organization_id, dry_run=True)
        previews = [item.to_dict() for item in preview.previews]
        # Özet isteğin alanlarını da kapsar. Bir davetin onayı başka davette kullanılamaz.
        current = digest_of(
            {
                "email": email.lower(),
                "first_name": first_name,
                "last_name": last_name,
                "organization_id": organization_id,
                "previews": previews,
            }
        )
        if dry_run:
            return 200, {"subject": preview.subject, "previews": previews, "preview_digest": current}
        if digest != current:
            return 409, {"error": "preview_changed"}
        result = keycloak.invite_user(email, first_name, last_name, organization_id)
        return 200, {"subject": result.subject, "previews": [item.to_dict() for item in result.previews]}


def make_server(
    app: App,
    verifier: Verifier,
    *,
    host: str,
    port: int,
    request_timeout: float = 10.0,
    clock: Callable[[], float] = time.time,
) -> HTTPServer:
    """Sunucuyu kurar. `verifier` servis belirtecini doğrular ve hatada `TokenRejected` yükseltir.

    `request_timeout`, bir isteğin başlığının ve gövdesinin okunabileceği toplam süredir.
    Birim saniyedir. `clock` imzanın zaman penceresi için kullanılır.
    """
    api = _Api(app)
    settings = app.settings
    secret = settings.webhook_secret.encode("utf-8")
    TokenHandler = Callable[[bytes, str], Reply]
    token_routes: dict[str, tuple[str, TokenHandler]] = {
        "/v1/reconcile": ("POST", api.post_reconcile),
        "/v1/dead-letters": ("GET", api.get_dead_letters),
        "/v1/dead-letters/replay": ("POST", api.post_replay),
        "/v1/invitations": ("POST", api.post_invitation),
    }
    methods = {"/healthz": "GET", "/v1/events": "POST", **{path: route[0] for path, route in token_routes.items()}}

    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "identity_sync"
        sys_version = ""
        # Yazarken de susan istemci sunucuyu tutamasın.
        timeout = request_timeout

        def setup(self) -> None:
            super().setup()
            # Sunucu tek iş parçacığıdır. Başlık ve gövde okuması toplam süreyle sınırlanır.
            self.rfile.close()
            deadline = time.monotonic() + request_timeout
            self.rfile = io.BufferedReader(_DeadlineReader(self.connection, deadline))

        def do_GET(self) -> None:
            status, body = self._guarded()
            raw = json.dumps(body).encode("utf-8")
            self.connection.settimeout(request_timeout)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_GET

        def _guarded(self) -> Reply:
            parts = urlsplit(self.path)
            try:
                return self._respond(parts.path, parse_qs(parts.query, keep_blank_values=True))
            except _BadRequest:
                return 400, {"error": "bad_request"}
            except _Forbidden:
                return 403, {"error": "forbidden"}
            except sqlite3.Error:
                _LOG.error("storage failed on %s", parts.path[:200])
                return 500, {"error": "storage_failed"}
            except (HttpError, TransportError) as error:
                _LOG.error("upstream failed on %s: %s", parts.path[:200], error)
                return 502, {"error": "upstream_failed"}

        def _respond(self, path: str, query: Query) -> Reply:
            expected = methods.get(path)
            if expected is None:
                self.close_connection = True  # gövde okunmadı
                return 404, {"error": "not_found"}
            if self.command != expected:
                self.close_connection = True
                return 405, {"error": "method_not_allowed"}
            if path == "/healthz":
                return 200, {"status": "ok"}
            body = self._read_body()
            if body is None:
                return 413, {"error": "too_large"}
            # Kimlik denetimi gövde yorumlanmadan önce yapılır.
            if path == "/v1/events":
                mode = _event_mode(query)
                if not self._signature_ok(body, mode):
                    return 401, {"error": "bad_signature"}
                return api.post_event(body, mode)
            azp = self._caller()
            if azp is None:
                return 401, {"error": "unauthorized"}
            if azp not in settings.known_azp:
                return 403, {"error": "forbidden"}
            return token_routes[path][1](body, azp)

        def _read_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if 0 <= length <= MAX_BODY_BYTES:
                body = self.rfile.read(length)
                if len(body) != length:
                    raise _BadRequest  # istemci gövdeyi tamamlamadan bağlantıyı kapattı
                return body
            if 0 < length <= _MAX_DRAIN_BYTES:
                self.rfile.read(length)  # istemci yanıtı okuyabilsin diye gövdeyi tüket
            else:
                self.close_connection = True
            return None

        def _signature_ok(self, body: bytes, mode: str) -> bool:
            """İmzayı, zaman penceresini ve tek kullanımı denetler.

            İmzalanan içerik `<zaman damgası>.<kip>.<gövde>` olur. Kip `execute` ya da `preview` olur.
            Böylece önizleme imzası yürütmede geçmez.
            """
            given = self.headers.get(SIGNATURE_HEADER, "")
            timestamp = self.headers.get(TIMESTAMP_HEADER, "")
            if not secret or not _TIMESTAMP.fullmatch(timestamp):
                return False
            message = f"{timestamp}.{mode}.".encode("ascii") + body
            expected = "sha256=" + hmac.new(secret, message, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
                return False
            now = clock()
            if abs(now - int(timestamp)) > SIGNATURE_WINDOW_SECONDS:
                return False
            # Aynı imza ikinci kez kullanılamaz. Kayıt pencere bitene kadar durur.
            expires_at = int(timestamp) + SIGNATURE_WINDOW_SECONDS + 1
            return app.store.claim_signature(expected, now=now, expires_at=expires_at)

        def _caller(self) -> str | None:
            """Belirteci doğrular ve çağıran istemcinin `azp` değerini döner."""
            # Hem çerez hem belirteç taşıyan istek reddedilir (`docs/sozlesmeler.md`, 3. bölüm).
            if self.headers.get("Cookie"):
                return None
            scheme, _, token = self.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                return None
            try:
                claims = verifier(token.strip())
            except TokenRejected:
                return None
            except Exception as error:  # doğrulayıcı çökerse istek yine reddedilir
                _LOG.error("token verifier failed: %s", type(error).__name__)
                return None
            azp = claims.get("azp") if isinstance(claims, Mapping) else None
            return azp if isinstance(azp, str) and azp else None

        def log_message(self, format: str, *args: object) -> None:
            # Günlüğe yalnız yol ve sayısal durum yazılır. Sorgu, gövde ve istemcinin metni yazılmaz.
            # Bozuk istekte `path` henüz yoktur.
            status = str(args[1]) if len(args) > 1 else ""
            path = urlsplit(getattr(self, "path", "")).path
            _LOG.info("%s %s", path[:200], status if status.isdigit() else "-")

    return HTTPServer((host, port), RequestHandler)
