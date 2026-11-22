"""Servisin HTTP uçları. Sözleşme `backend/contracts/identity_sync.openapi.yaml` dosyasındadır.

Sunucu Python'un kendi `http.server` modülüdür ve istekleri tek tek işler.
Bu sıra aynı kullanıcının iki olayının çakışmasını önler.

Olay ucu imza ister. Öteki uçlar servis belirteci ister.
Elle başlatılan her komutun burada bir ucu vardır (`docs/sozlesmeler.md`, 10. bölüm).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import sqlite3
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from identity_sync.app import App
from identity_sync.auth import TokenRejected, Verifier
from identity_sync.events import EventError, from_keycloak, looks_like_keycloak, parse_event
from identity_sync.httpjson import HttpError, TransportError

__all__ = ["TokenRejected", "make_server"]

MAX_BODY_BYTES = 65536
_MAX_DRAIN_BYTES = 1024 * 1024
SIGNATURE_HEADER = "X-Identity-Sync-Signature"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}$")
_LOG = logging.getLogger("identity_sync")

Reply = tuple[int, object]


class _BadRequest(Exception):
    pass


def _json_object(body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _BadRequest from None
    if not isinstance(payload, dict):
        raise _BadRequest
    return payload


def _dry_run(payload: Mapping[str, object]) -> bool:
    """Çağıran önizleme mi yoksa yürütme mi istediğini açıkça yazmalıdır."""
    value = payload.get("dry_run")
    if not isinstance(value, bool):
        raise _BadRequest
    return value


def _text(payload: Mapping[str, object], name: str, *, required: bool = False, max_length: int = 150) -> str:
    value = payload.get(name, None if required else "")
    if not isinstance(value, str) or len(value) > max_length or (required and not value):
        raise _BadRequest
    return value


class _Api:
    """Uçların iş kısmı. HTTP ayrıntısını bilmez."""

    def __init__(self, app: App) -> None:
        self._app = app

    def post_event(self, body: bytes, query: Mapping[str, list[str]]) -> Reply:
        payload = _json_object(body)
        try:
            event = parse_event(from_keycloak(payload) if looks_like_keycloak(payload) else payload)
        except EventError:
            raise _BadRequest from None
        if query.get("dry_run") == ["true"]:
            return 200, self._app.processor.handle(event, dry_run=True).to_dict()
        return 202, self._app.processor.handle(event).to_dict()

    def post_reconcile(self, _body: bytes, _query: Mapping[str, list[str]]) -> Reply:
        differences = [difference.to_dict() for difference in self._app.reconcile()]
        return 200, {"count": len(differences), "differences": differences}

    def get_dead_letters(self, _body: bytes, _query: Mapping[str, list[str]]) -> Reply:
        return 200, {"dead_letters": [letter.to_dict() for letter in self._app.store.dead_letters()]}

    def post_replay(self, body: bytes, _query: Mapping[str, list[str]]) -> Reply:
        dry_run = _dry_run(_json_object(body))
        results = self._app.processor.replay_dead_letters(dry_run=dry_run)
        return 200, {"results": [{"event_id": event_id, **result.to_dict()} for event_id, result in results]}

    def post_invitation(self, body: bytes, _query: Mapping[str, list[str]]) -> Reply:
        payload = _json_object(body)
        dry_run = _dry_run(payload)
        email = _text(payload, "email", required=True, max_length=254)
        if not _EMAIL.fullmatch(email):
            raise _BadRequest
        result = self._app.keycloak.invite_user(
            email,
            _text(payload, "first_name"),
            _text(payload, "last_name"),
            _text(payload, "organization_id", required=True),
            dry_run=dry_run,
        )
        return 200, {"subject": result.subject, "previews": [preview.to_dict() for preview in result.previews]}


def make_server(app: App, verifier: Verifier, *, host: str, port: int) -> HTTPServer:
    """Sunucuyu kurar. `verifier` servis belirtecini doğrular ve hatada `TokenRejected` yükseltir."""
    api = _Api(app)
    secret = app.settings.webhook_secret.encode("utf-8")
    Handler = Callable[[bytes, Mapping[str, list[str]]], Reply]
    # yol -> (yöntem, kimlik türü, işlev)
    routes: dict[str, tuple[str, str, Handler]] = {
        "/v1/events": ("POST", "signature", api.post_event),
        "/v1/reconcile": ("POST", "token", api.post_reconcile),
        "/v1/dead-letters": ("GET", "token", api.get_dead_letters),
        "/v1/dead-letters/replay": ("POST", "token", api.post_replay),
        "/v1/invitations": ("POST", "token", api.post_invitation),
    }

    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "identity_sync"
        sys_version = ""

        def do_GET(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def _dispatch(self) -> None:
            parts = urlsplit(self.path)
            status, body = self._respond(parts.path, parse_qs(parts.query))
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _respond(self, path: str, query: Mapping[str, list[str]]) -> Reply:
            if path == "/healthz":
                return (200, {"status": "ok"}) if self.command == "GET" else (405, {"error": "method_not_allowed"})
            route = routes.get(path)
            if route is None:
                return 404, {"error": "not_found"}
            method, credential, handler = route
            if self.command != method:
                return 405, {"error": "method_not_allowed"}
            body = self._read_body()
            if body is None:
                return 413, {"error": "too_large"}
            # Kimlik denetimi gövde yorumlanmadan önce yapılır.
            if credential == "signature":
                if not self._signature_ok(body):
                    return 401, {"error": "bad_signature"}
            elif not self._token_ok():
                return 401, {"error": "unauthorized"}
            try:
                return handler(body, query)
            except _BadRequest:
                return 400, {"error": "bad_request"}
            except sqlite3.Error:
                _LOG.error("storage failed on %s", path)
                return 500, {"error": "storage_failed"}
            except (HttpError, TransportError) as error:
                _LOG.error("upstream failed on %s: %s", path, error)
                return 502, {"error": "upstream_failed"}

        def _read_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if 0 <= length <= MAX_BODY_BYTES:
                return self.rfile.read(length)
            if 0 < length <= _MAX_DRAIN_BYTES:
                self.rfile.read(length)  # istemci yanıtı okuyabilsin diye gövdeyi tüket
            else:
                self.close_connection = True
            return None

        def _signature_ok(self, body: bytes) -> bool:
            given = self.headers.get(SIGNATURE_HEADER, "")
            expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
            return bool(secret) and hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))

        def _token_ok(self) -> bool:
            # Hem çerez hem belirteç taşıyan istek reddedilir (`docs/sozlesmeler.md`, 3. bölüm).
            if self.headers.get("Cookie"):
                return False
            scheme, _, token = self.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                return False
            try:
                verifier(token.strip())
            except TokenRejected:
                return False
            return True

        def log_message(self, format: str, *args: object) -> None:
            # Günlüğe yalnız yöntem, yol ve durum yazılır. Sorgu ve gövde yazılmaz.
            _LOG.info("%s %s %s", self.command, urlsplit(self.path).path, args[1] if len(args) > 1 else "")

    return HTTPServer((host, port), RequestHandler)
