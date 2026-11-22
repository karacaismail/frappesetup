"""HTTP uçlarının testleri. İstekler gerçek HTTP yolundan gider (D-6).

Beklenen durum kodlarının kaynağı `contracts/identity_sync.openapi.yaml` dosyasıdır.
Yazma kurallarının kaynağı `docs/sozlesmeler.md` dosyasının 10. bölümüdür.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request

from identity_sync.events import Event
from identity_sync.server import TokenRejected, make_server

from . import fakes
from .fakes import DONE, ORG_ID, REALM_ID, SUBJECT, WEBHOOK_SECRET, Stack, keycloak_user

NOW = 1_795_000_000
PREVIEW_TOKEN = "preview-token"  # yapay zekâ aracısının belirteci: yalnız okur ve önizler
EXECUTE_TOKEN = "execute-token"  # onay katmanının belirteci: yürütebilir
SESSION_TOKEN = "session-token"  # the service token of tenant kiraci1: may only revoke sessions
OTHER_SITE_TOKEN = "other-site-token"  # the service token of tenant kiraci2
PRESS_TOKEN = "press-token"  # the Press service token: may only request an account deletion
EVENT = {"id": "e-1", "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 1, "user_id": SUBJECT}
ALL_ACTIONS = ["press.ensure_team", "tenant.change_email", "tenant.provision"]


def fake_verifier(token: str) -> dict[str, object]:
    azp = {
        PREVIEW_TOKEN: "ai-agent",
        EXECUTE_TOKEN: "approval-service",
        SESSION_TOKEN: "site-kiraci1-service",
        OTHER_SITE_TOKEN: "site-kiraci2-service",
        PRESS_TOKEN: "press-service",
        "stranger-token": "baska-istemci",
    }.get(token)
    if azp is None:
        raise TokenRejected("invalid_signature")
    return {"azp": azp, "aud": "identity-sync"}


def sign(body: bytes, timestamp: int, mode: str = "execute", secret: str = WEBHOOK_SECRET) -> str:
    message = f"{timestamp}.{mode}.".encode() + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class ServerCase(unittest.TestCase):
    request_timeout = 0.5
    two_tenants = False

    def setUp(self) -> None:
        self.stack = Stack(two_tenants=self.two_tenants)
        self.addCleanup(self.stack.close)
        self.now = float(NOW)
        self.start_server(fake_verifier)
        self.stack.keycloak.add_user(keycloak_user(), [{"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}])
        self._next_timestamp = NOW - 100

    def start_server(self, verifier) -> None:
        self.httpd = make_server(
            self.stack.app,
            verifier,
            host="127.0.0.1",
            port=0,
            request_timeout=self.request_timeout,
            clock=lambda: self.now,
        )
        thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"

    def call(
        self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> tuple[int, object]:
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            with error:  # the error owns the response; close it
                return error.code, json.loads(error.read() or b"null")

    def timestamp(self) -> int:
        # Her isteğin imzası ayrı olsun diye zaman damgası ilerler.
        self._next_timestamp += 1
        return self._next_timestamp

    def post_event(self, payload: object = EVENT, *, dry_run: bool = False, path: str | None = None, mode=None):
        body = json.dumps(payload).encode()
        timestamp = self.timestamp()
        headers = {
            "Content-Type": "application/json",
            "X-Identity-Sync-Timestamp": str(timestamp),
            "X-Identity-Sync-Signature": sign(body, timestamp, mode or ("preview" if dry_run else "execute")),
        }
        target = path or ("/v1/events?dry_run=true" if dry_run else "/v1/events")
        return self.call("POST", target, body, headers)

    def post_event_raw(self, body: bytes) -> tuple[int, object]:
        timestamp = self.timestamp()
        headers = {"X-Identity-Sync-Timestamp": str(timestamp), "X-Identity-Sync-Signature": sign(body, timestamp)}
        return self.call("POST", "/v1/events", body, headers)

    def bearer(self, token: str = EXECUTE_TOKEN) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def post_json(self, path: str, payload: object, token: str = EXECUTE_TOKEN) -> tuple[int, object]:
        return self.call("POST", path, json.dumps(payload).encode(), self.bearer(token))

    def downstream_writes(self) -> list[fakes.Recorded]:
        return self.stack.press.writes() + self.stack.tenant.writes()

    def keycloak_writes(self) -> list[fakes.Recorded]:
        return [r for r in self.stack.keycloak.requests if r.method != "GET" and "/admin/" in r.path]


class HealthTest(ServerCase):
    def test_health_needs_no_credentials(self) -> None:
        self.assertEqual(self.call("GET", "/healthz"), (200, {"status": "ok"}))

    def test_unknown_path(self) -> None:
        self.assertEqual(self.call("GET", "/yok"), (404, {"error": "not_found"}))

    def test_wrong_method(self) -> None:
        self.assertEqual(self.call("GET", "/v1/events"), (405, {"error": "method_not_allowed"}))

    def test_unsupported_methods_get_json_405(self) -> None:
        for method in ("PUT", "DELETE", "PATCH"):
            with self.subTest(method=method):
                self.assertEqual(self.call(method, "/v1/events"), (405, {"error": "method_not_allowed"}))


class EventEndpointTest(ServerCase):
    def test_signed_event_is_processed(self) -> None:
        status, body = self.post_event()

        self.assertEqual((status, body), (202, {"status": "processed", "actions": ALL_ACTIONS}))
        self.assertEqual(len(self.downstream_writes()), 3)

    def test_second_delivery_is_a_duplicate(self) -> None:
        self.post_event()

        status, body = self.post_event()

        self.assertEqual((status, body["status"]), (202, "duplicate"))
        self.assertEqual(len(self.downstream_writes()), 3)

    def test_invalid_json_is_bad_request(self) -> None:
        body, timestamp = b"{bozuk", self.timestamp()
        headers = {"X-Identity-Sync-Timestamp": str(timestamp), "X-Identity-Sync-Signature": sign(body, timestamp)}

        self.assertEqual(self.call("POST", "/v1/events", body, headers), (400, {"error": "bad_request"}))

    def test_missing_field_is_bad_request(self) -> None:
        self.assertEqual(self.post_event({"id": "e-1", "kind": "user"}), (400, {"error": "bad_request"}))

    def test_large_body_is_rejected_before_processing(self) -> None:
        status, reply = self.post_event({**EVENT, "dolgu": "x" * 70000})

        self.assertEqual((status, reply), (413, {"error": "too_large"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_failed_delivery_is_accepted_and_queued(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))

        status, body = self.post_event()

        self.assertEqual((status, body["status"]), (202, "dead_lettered"))

    def test_dry_run_returns_preview_and_writes_nothing(self) -> None:
        status, body = self.post_event(dry_run=True)

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "preview")
        self.assertEqual([p["operation"] for p in body["previews"]], ALL_ACTIONS)
        self.assertEqual([p["destructive"] for p in body["previews"]], [False, False, False])
        self.assertEqual(self.downstream_writes(), [])

    def test_unclear_dry_run_value_never_executes(self) -> None:
        # Sözleşme yalnız `true` ve `false` değerini kabul eder.
        for query in ("dry_run=True", "dry_run=1", "dry_run=true&dry_run=true", "dry_run=", "dry_run=true&dry_run=false"):
            with self.subTest(query=query):
                for mode in ("execute", "preview"):
                    status, _reply = self.post_event(path=f"/v1/events?{query}", mode=mode)
                    self.assertIn(status, (400, 401))
        self.assertEqual(self.downstream_writes(), [])

    def test_dry_run_false_executes(self) -> None:
        status, body = self.post_event(path="/v1/events?dry_run=false")

        self.assertEqual((status, body["status"]), (202, "processed"))


class SignatureTest(ServerCase):
    """İmza zaman damgasını ve yürütme seçimini kapsar. Aynı imza iki kez kullanılamaz."""

    def send(self, body: bytes, timestamp: int | None, signature: str | None, path: str = "/v1/events"):
        headers = {"Content-Type": "application/json"}
        if timestamp is not None:
            headers["X-Identity-Sync-Timestamp"] = str(timestamp)
        if signature is not None:
            headers["X-Identity-Sync-Signature"] = signature
        return self.call("POST", path, body, headers)

    def assert_rejected(self, reply: tuple[int, object]) -> None:
        self.assertEqual(reply, (401, {"error": "bad_signature"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_missing_signature_is_rejected(self) -> None:
        self.assert_rejected(self.send(json.dumps(EVENT).encode(), NOW, None))

    def test_missing_timestamp_is_rejected(self) -> None:
        body = json.dumps(EVENT).encode()
        self.assert_rejected(self.send(body, None, sign(body, NOW)))

    def test_wrong_secret_is_rejected(self) -> None:
        body = json.dumps(EVENT).encode()
        self.assert_rejected(self.send(body, NOW, sign(body, NOW, secret="baska-anahtar")))

    def test_signature_of_other_body_is_rejected(self) -> None:
        other = json.dumps({**EVENT, "id": "e-2"}).encode()
        self.assert_rejected(self.send(json.dumps(EVENT).encode(), NOW, sign(other, NOW)))

    def test_body_only_signature_is_rejected(self) -> None:
        # Eski biçim yalnız gövdeyi imzalardı.
        body = json.dumps(EVENT).encode()
        old = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.assert_rejected(self.send(body, NOW, old))

    def test_preview_signature_cannot_execute(self) -> None:
        # Önizleme isteğini ele geçiren kişi sorgu alanını silerek yürütemez.
        body = json.dumps(EVENT).encode()
        preview_signature = sign(body, NOW, "preview")

        self.assert_rejected(self.send(body, NOW, preview_signature, "/v1/events"))
        self.assert_rejected(self.send(body, NOW, preview_signature, "/v1/events?dry_run=false"))

    def test_execute_signature_cannot_be_downgraded_to_preview(self) -> None:
        body = json.dumps(EVENT).encode()
        self.assert_rejected(self.send(body, NOW, sign(body, NOW, "execute"), "/v1/events?dry_run=true"))

    def test_timestamp_outside_window_is_rejected(self) -> None:
        body = json.dumps(EVENT).encode()
        for timestamp in (NOW - 301, NOW + 301):
            with self.subTest(timestamp=timestamp):
                self.assert_rejected(self.send(body, timestamp, sign(body, timestamp)))

    def test_timestamp_at_window_edge_is_accepted(self) -> None:
        body = json.dumps(EVENT).encode()
        self.assertEqual(self.send(body, NOW - 300, sign(body, NOW - 300))[0], 202)

    def test_tampered_timestamp_is_rejected(self) -> None:
        body = json.dumps(EVENT).encode()
        self.assert_rejected(self.send(body, NOW, sign(body, NOW - 5)))

    def test_non_numeric_timestamp_is_rejected(self) -> None:
        body = json.dumps(EVENT).encode()
        headers = {"X-Identity-Sync-Timestamp": "abc", "X-Identity-Sync-Signature": sign(body, NOW)}
        self.assert_rejected(self.call("POST", "/v1/events", body, headers))

    def test_same_signature_is_rejected_the_second_time(self) -> None:
        body = json.dumps(EVENT).encode()
        signature = sign(body, NOW)

        self.assertEqual(self.send(body, NOW, signature)[0], 202)
        writes = len(self.downstream_writes())
        second = self.send(body, NOW, signature)

        self.assertEqual(second, (401, {"error": "bad_signature"}))
        self.assertEqual(len(self.downstream_writes()), writes)

    def test_preview_signature_is_single_use_too(self) -> None:
        body = json.dumps(EVENT).encode()
        signature = sign(body, NOW, "preview")

        self.assertEqual(self.send(body, NOW, signature, "/v1/events?dry_run=true")[0], 200)
        self.assertEqual(self.send(body, NOW, signature, "/v1/events?dry_run=true")[0], 401)

    def test_service_token_does_not_open_event_endpoint(self) -> None:
        status, _reply = self.call("POST", "/v1/events", json.dumps(EVENT).encode(), self.bearer())

        self.assertEqual(status, 401)


class ForkedListenerTest(ServerCase):
    """The Keycloak event listener fork of the kimlik-realm job (gap list, item 1).

    FORK_BODY is built the way the fork's EventPayloads builds a user event. FORK_SIGNATURE was
    produced by the fork's own WebhookSigner.java (kimlik-realm branch, commit 750e384) for
    the secret "test-webhook-secret", the timestamp 1795000000 and the mode "execute".
    It is not computed by this code base, so it is an independent expected value.
    """

    FORK_BODY = b'{"id":"k-fork-1","time":1795000000000,"type":"VERIFY_EMAIL","realmId":"7c9e6679-7425-40de-944b-e07fc1f90ae7","clientId":"press","userId":"11111111-1111-4111-8111-111111111111"}'
    FORK_SIGNATURE = "sha256=164ff260a1cd1aa8e32a399124f096ce4b759a43dee1c0aa4fe3aa8832c18e30"

    def send(self, body: bytes, signature: str, timestamp: int = NOW) -> tuple[int, object]:
        headers = {
            "Content-Type": "application/json",
            "X-Identity-Sync-Timestamp": str(timestamp),
            "X-Identity-Sync-Signature": signature,
        }
        return self.call("POST", "/v1/events", body, headers)

    def test_signature_made_by_the_fork_is_accepted(self) -> None:
        status, body = self.send(self.FORK_BODY, self.FORK_SIGNATURE)

        self.assertEqual((status, body["status"]), (202, "processed"))

    def test_python_helper_and_fork_agree(self) -> None:
        self.assertEqual(sign(self.FORK_BODY, NOW, "execute"), self.FORK_SIGNATURE)

    def test_broken_fork_signature_is_rejected(self) -> None:
        broken = self.FORK_SIGNATURE[:-1] + ("0" if self.FORK_SIGNATURE[-1] != "0" else "1")

        self.assertEqual(self.send(self.FORK_BODY, broken), (401, {"error": "bad_signature"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_old_fork_timestamp_is_rejected(self) -> None:
        # The fork signed at NOW. The server clock is 301 seconds later.
        self.now = float(NOW + 301)

        self.assertEqual(self.send(self.FORK_BODY, self.FORK_SIGNATURE), (401, {"error": "bad_signature"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_fork_signature_does_not_fit_a_changed_body(self) -> None:
        changed = self.FORK_BODY.replace(b"k-fork-1", b"k-fork-2")

        self.assertEqual(self.send(changed, self.FORK_SIGNATURE), (401, {"error": "bad_signature"}))


class KeycloakFormatTest(ServerCase):
    """Keycloak'ın kendi olay biçimi. `realmId` realm'in iç kimliğidir, adı değildir."""

    def test_native_event_with_configured_realm_id_is_processed(self) -> None:
        native = {"id": "k-1", "time": 1, "type": "VERIFY_EMAIL", "realmId": REALM_ID, "userId": SUBJECT}

        status, body = self.post_event(native)

        self.assertEqual((status, body["status"]), (202, "processed"))

    def test_native_event_of_other_realm_is_ignored(self) -> None:
        native = {"id": "k-1", "time": 1, "type": "VERIFY_EMAIL", "realmId": "baska-realm-kimligi", "userId": SUBJECT}

        status, body = self.post_event(native)

        self.assertEqual((status, body["status"]), (202, "ignored"))
        self.assertEqual(self.downstream_writes(), [])

    def test_realm_name_in_realm_id_field_is_not_trusted(self) -> None:
        # Realm adı `platform` olur. Kimlik alanında ad gelirse olay bu realm'in sayılmaz.
        native = {"id": "k-1", "time": 1, "type": "VERIFY_EMAIL", "realmId": "platform", "userId": SUBJECT}

        status, body = self.post_event(native)

        self.assertEqual((status, body["status"]), (202, "ignored"))

    def test_membership_create_without_user_is_ignored(self) -> None:
        # Keycloak 26.8.2 üye ekleme olayında kullanıcıyı vermez. Servis bu olayı işleyemez.
        native = {
            "id": "k-9",
            "time": 1,
            "realmId": REALM_ID,
            "operationType": "CREATE",
            "resourceType": "ORGANIZATION_MEMBERSHIP",
            "resourcePath": f"organizations/{ORG_ID}/members",
        }
        ignored = {"status": "ignored", "actions": []}

        self.assertEqual(self.post_event(native), (202, ignored))
        # Önizleme isteği sözleşmedeki gibi 200 döner.
        self.assertEqual(self.post_event({**native, "id": "k-10"}, dry_run=True), (200, ignored))
        self.assertEqual(self.downstream_writes(), [])


class RawSocketTest(ServerCase):
    """Bozuk ve yavaş istemciler sunucuyu durdurmamalıdır."""

    def raw(self, data: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as sock:
            sock.sendall(data)
            chunks = []
            while chunk := sock.recv(65536):
                chunks.append(chunk)
            return b"".join(chunks)

    def test_garbage_request_line_gets_an_answer(self) -> None:
        reply = self.raw(b"GARBAGE\r\n\r\n")

        self.assertIn(b"400", reply.split(b"\r\n", 1)[0])
        self.assertEqual(self.call("GET", "/healthz")[0], 200)

    def test_stalled_client_does_not_block_the_server(self) -> None:
        stalled = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        self.addCleanup(stalled.close)
        stalled.sendall(b"POST /v1/events HTTP/1.1\r\nContent-Length: 100\r\n\r\n")

        self.assertEqual(self.call("GET", "/healthz"), (200, {"status": "ok"}))

    def drip(self, data: bytes, stop: threading.Event) -> None:
        # Her 0,1 saniyede bir bayt gönderir. Bekleme süresi hiç dolmaz, toplam süre dolar.
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=10) as sock:
                for index in range(len(data)):
                    if stop.is_set():
                        return
                    sock.sendall(data[index : index + 1])
                    time.sleep(0.1)
        except OSError:
            return  # sunucu bağlantıyı kapattı: beklenen sonuç

    def assert_health_answers_despite(self, slow_request: bytes) -> None:
        stop = threading.Event()
        thread = threading.Thread(target=self.drip, args=(slow_request, stop), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(stop.set)
        time.sleep(0.15)  # yavaş istemci sunucuya ilk ulaşan olsun
        started = time.monotonic()

        reply = self.call("GET", "/healthz")

        self.assertEqual(reply, (200, {"status": "ok"}))
        # Toplam sınır 0,5 saniyedir. Sınır olmasa bu istek 10 saniyeden uzun beklerdi.
        self.assertLess(time.monotonic() - started, 3.0)

    def test_slow_headers_hit_the_total_deadline(self) -> None:
        self.assert_health_answers_despite(b"POST /v1/events HTTP/1.1\r\n" + b"X-Dolgu: " + b"a" * 200 + b"\r\n\r\n")

    def test_slow_body_hits_the_total_deadline(self) -> None:
        self.assert_health_answers_despite(b"POST /v1/events HTTP/1.1\r\nContent-Length: 200\r\n\r\n" + b"x" * 200)

    def test_deeply_nested_body_is_a_bad_request(self) -> None:
        self.assertEqual(self.post_event_raw(b"[" * 100000 + b"]" * 100000)[0], 413)
        self.assertEqual(self.post_event_raw(b"[" * 30000 + b"]" * 30000), (400, {"error": "bad_request"}))

    def test_bad_content_length_is_rejected(self) -> None:
        for value in (b"-1", b"abc", b"99999999", b"+5", b"1_0"):
            with self.subTest(value=value):
                reply = self.raw(b"POST /v1/events HTTP/1.1\r\nContent-Length: " + value + b"\r\n\r\n")
                self.assertIn(b" 413 ", reply.split(b"\r\n", 1)[0])
        self.assertEqual(self.downstream_writes(), [])


class ServiceTokenTest(ServerCase):
    PROTECTED = (
        ("POST", "/v1/reconcile", b'{"dry_run": true}'),
        ("GET", "/v1/dead-letters", None),
        ("POST", "/v1/dead-letters/replay", b'{"dry_run": true}'),
        ("POST", "/v1/invitations", b'{"email": "a@example.test", "organization_id": "o", "dry_run": true}'),
    )

    def test_missing_token_is_rejected(self) -> None:
        for method, path, body in self.PROTECTED:
            with self.subTest(path=path):
                status, reply = self.call(method, path, body, {"Content-Type": "application/json"})
                self.assertEqual((status, reply), (401, {"error": "unauthorized"}))

    def test_invalid_token_is_rejected(self) -> None:
        for method, path, body in self.PROTECTED:
            with self.subTest(path=path):
                status, reply = self.call(method, path, body, self.bearer("kotu-token"))
                self.assertEqual((status, reply), (401, {"error": "unauthorized"}))
        self.assertEqual(self.downstream_writes() + self.keycloak_writes(), [])

    def test_valid_token_of_unlisted_client_is_forbidden(self) -> None:
        for method, path, body in self.PROTECTED:
            with self.subTest(path=path):
                status, reply = self.call(method, path, body, self.bearer("stranger-token"))
                self.assertEqual((status, reply), (403, {"error": "forbidden"}))

    def test_webhook_signature_does_not_open_protected_endpoints(self) -> None:
        body = b'{"dry_run": true}'
        headers = {"X-Identity-Sync-Timestamp": str(NOW), "X-Identity-Sync-Signature": sign(body, NOW)}

        self.assertEqual(self.call("POST", "/v1/dead-letters/replay", body, headers)[0], 401)

    def test_verifier_crash_is_a_rejection(self) -> None:
        # Doğrulayıcı beklenmeyen hata verirse istek yine reddedilir. Örneğin anahtar listesi alınamadı.
        def broken(_token: str) -> dict[str, object]:
            raise RuntimeError("jwks down")

        self.start_server(broken)

        self.assertEqual(self.call("GET", "/v1/dead-letters", None, self.bearer()), (401, {"error": "unauthorized"}))

    def test_request_with_cookie_and_token_is_rejected(self) -> None:
        headers = {**self.bearer(), "Cookie": "sid=abc"}

        self.assertEqual(self.call("GET", "/v1/dead-letters", None, headers)[0], 401)


class ApprovalLayerTest(ServerCase):
    """Yapay zekâ yalnız önizler. Yürütmeyi yalnız onay katmanı başlatır (sözleşme, 10. bölüm)."""

    def fail_once(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.post_event()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, DONE)

    def fail_twice_more(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.post_event({**EVENT, "id": "e-2"})
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, DONE)

    def preview_replay(self, token: str = PREVIEW_TOKEN) -> dict[str, object]:
        status, body = self.post_json("/v1/dead-letters/replay", {"dry_run": True}, token)
        self.assertEqual(status, 200)
        return body

    def execute_replay(self, digest: object, token: str = EXECUTE_TOKEN, approval_id: object = "onay-1"):
        payload = {"dry_run": False, "preview_digest": digest, "approval_id": approval_id}
        return self.post_json("/v1/dead-letters/replay", payload, token)

    def test_agent_can_read_and_preview(self) -> None:
        self.fail_once()

        self.assertEqual(self.call("GET", "/v1/dead-letters", None, self.bearer(PREVIEW_TOKEN))[0], 200)
        preview = self.preview_replay()

        self.assertEqual(preview["results"][0]["status"], "preview")
        self.assertRegex(preview["preview_digest"], r"^[0-9a-f]{64}$")

    def test_agent_cannot_execute(self) -> None:
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        writes = len(self.downstream_writes())

        status, reply = self.execute_replay(digest, token=PREVIEW_TOKEN)

        self.assertEqual((status, reply), (403, {"error": "forbidden"}))
        self.assertEqual(len(self.downstream_writes()), writes)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

    def test_approval_layer_executes_the_previewed_plan(self) -> None:
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]

        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, body = self.execute_replay(digest)

        self.assertEqual(status, 200)
        self.assertEqual(body["results"][0]["status"], "processed")
        self.assertEqual(self.stack.app.store.dead_letters(), [])
        # İşlem günlüğü çağıranı, onay kimliğini, önizleme özetini ve sonucu taşır.
        audit = "\n".join(logs.output)
        self.assertIn("replay_dead_letters", audit)
        self.assertIn("approval-service", audit)
        self.assertIn("onay-1", audit)
        self.assertIn(digest, audit)
        self.assertIn("outcome=executed", audit)

    def test_approval_id_works_only_once(self) -> None:
        # An existing user's invitation plan stays the same after the first run.
        # Without single use, the same approval would send the invitation e-mail again.
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, [keycloak_user(email="davetli@example.test")]))
        kc.on("POST", f"{kc.admin}/organizations/{ORG_ID}/members", (201, None))
        email_path = f"{kc.admin}/users/{SUBJECT}/execute-actions-email"
        kc.on("PUT", email_path, (204, None))
        invitation = {"email": "davetli@example.test", "organization_id": ORG_ID}
        _status, preview = self.post_json("/v1/invitations", {**invitation, "dry_run": True})
        execute = {**invitation, "dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-9"}

        self.assertEqual(self.post_json("/v1/invitations", execute)[0], 200)
        second = self.post_json("/v1/invitations", execute)

        self.assertEqual(second, (409, {"error": "approval_used"}))
        self.assertEqual(len(kc.calls("PUT", email_path)), 1)

    def test_used_approval_cannot_authorise_another_operation(self) -> None:
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        self.assertEqual(self.execute_replay(digest, approval_id="onay-7")[0], 200)
        self.fail_twice_more()
        other_digest = self.preview_replay()["preview_digest"]
        writes = len(self.downstream_writes())

        status, reply = self.execute_replay(other_digest, approval_id="onay-7")

        self.assertEqual((status, reply), (409, {"error": "approval_used"}))
        self.assertEqual(len(self.downstream_writes()), writes)

    def test_approval_is_consumed_even_when_the_plan_changed(self) -> None:
        # A changed plan needs a new preview and a new approval. The old approval is spent.
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [])
        self.assertEqual(self.execute_replay(digest, approval_id="onay-8")[0], 409)
        fresh = self.preview_replay()["preview_digest"]

        self.assertEqual(self.execute_replay(fresh, approval_id="onay-8"), (409, {"error": "approval_used"}))
        self.assertEqual(self.execute_replay(fresh, approval_id="onay-8b")[0], 200)

    def test_refused_client_does_not_consume_the_approval(self) -> None:
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        self.assertEqual(self.execute_replay(digest, token=PREVIEW_TOKEN, approval_id="onay-6")[0], 403)

        self.assertEqual(self.execute_replay(digest, approval_id="onay-6")[0], 200)

    def test_changed_email_after_preview_is_refused(self) -> None:
        # Same operations, other field values. The digest covers the values that get written.
        self.fail_once()
        preview = self.preview_replay()
        self.stack.keycloak.add_user(
            keycloak_user(email="yeni@example.test"), [{"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}]
        )
        writes = len(self.downstream_writes())

        status, reply = self.execute_replay(preview["preview_digest"])

        self.assertEqual((status, reply), (409, {"error": "preview_changed"}))
        self.assertEqual(len(self.downstream_writes()), writes)
        self.assertNotIn("example.test", json.dumps(preview))

    def test_refused_execution_is_logged_as_refused(self) -> None:
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [])

        with self.assertLogs("identity_sync", level="INFO") as logs:
            self.execute_replay(digest)
            self.execute_replay(digest, token=PREVIEW_TOKEN)

        audit = "\n".join(logs.output)
        self.assertIn("outcome=preview_changed", audit)
        self.assertIn("outcome=forbidden", audit)
        self.assertNotIn("outcome=executed", audit)

    def test_redelivered_unknown_event_is_not_executed_again(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (202, {"message": {"status": "queued"}}))
        self.post_event()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, DONE)
        writes = len(self.downstream_writes())

        status, body = self.post_event()

        self.assertEqual((status, body["status"]), (202, "unknown"))
        self.assertEqual(len(self.downstream_writes()), writes)

    def test_execution_without_digest_or_approval_is_bad_request(self) -> None:
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        for payload in (
            {"dry_run": False},
            {"dry_run": False, "preview_digest": digest},
            {"dry_run": False, "approval_id": "onay-1"},
            {"dry_run": False, "preview_digest": digest, "approval_id": ""},
            {"dry_run": False, "preview_digest": "kisa", "approval_id": "onay-1"},
            {},
        ):
            with self.subTest(payload=payload):
                status, reply = self.post_json("/v1/dead-letters/replay", payload)
                self.assertEqual((status, reply), (400, {"error": "bad_request"}))
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

    def test_execution_is_refused_when_plan_changed_after_preview(self) -> None:
        # İnsan "kullanıcıyı hazırla" planını onayladı. Kullanıcı sonra kapatıldı. Plan artık yıkıcıdır.
        self.fail_once()
        digest = self.preview_replay()["preview_digest"]
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [])
        writes = len(self.downstream_writes())

        status, reply = self.execute_replay(digest)

        self.assertEqual((status, reply), (409, {"error": "preview_changed"}))
        self.assertEqual(len(self.downstream_writes()), writes)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

    def test_invitation_preview_then_execute(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, []))
        kc.on("POST", f"{kc.admin}/users", (201, None, {"Location": f"{kc.url}{kc.admin}/users/yeni-kullanici"}))
        kc.on("POST", f"{kc.admin}/organizations/{ORG_ID}/members", (201, None))
        kc.on("PUT", f"{kc.admin}/users/yeni-kullanici/execute-actions-email", (204, None))
        invitation = {"email": "davetli@example.test", "first_name": "Deniz", "organization_id": ORG_ID}

        status, preview = self.post_json("/v1/invitations", {**invitation, "dry_run": True}, PREVIEW_TOKEN)
        self.assertEqual(status, 200)
        self.assertIsNone(preview["subject"])
        self.assertEqual(
            [p["operation"] for p in preview["previews"]],
            ["keycloak.create_user", "keycloak.add_organization_member", "keycloak.send_execute_actions_email"],
        )
        self.assertEqual(self.keycloak_writes(), [])

        execute = {**invitation, "dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-2"}
        self.assertEqual(self.post_json("/v1/invitations", execute, PREVIEW_TOKEN), (403, {"error": "forbidden"}))
        self.assertEqual(self.keycloak_writes(), [])

        status, body = self.post_json("/v1/invitations", execute)
        self.assertEqual((status, body["subject"]), (200, "yeni-kullanici"))
        self.assertEqual(len(self.keycloak_writes()), 3)

    def test_invitation_digest_is_bound_to_the_request(self) -> None:
        # Bir davetin onayı başka kuruluşa davet için kullanılamaz.
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, []))
        invitation = {"email": "davetli@example.test", "organization_id": ORG_ID}
        _status, preview = self.post_json("/v1/invitations", {**invitation, "dry_run": True})
        other = {**invitation, "organization_id": "baska-kurulus", "dry_run": False}
        other.update(preview_digest=preview["preview_digest"], approval_id="onay-3")

        self.assertEqual(self.post_json("/v1/invitations", other), (409, {"error": "preview_changed"}))
        self.assertEqual(self.keycloak_writes(), [])

    def test_invitation_input_is_validated(self) -> None:
        for payload in (
            {"email": "davetli@example.test", "organization_id": ORG_ID},
            {"email": "eposta-degil", "organization_id": ORG_ID, "dry_run": True},
            {"email": "davetli@example.test", "organization_id": "..", "dry_run": True},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.post_json("/v1/invitations", payload)[0], 400)
        self.assertEqual(self.stack.keycloak.requests, [])


class SessionRevokeTest(ServerCase):
    """POST /v1/sessions/revoke (docs/sozlesmeler.md, section 7).

    Two tenants share one Keycloak realm. A tenant may only end the session of a user who is
    a member of its own organization, and only a session that belongs to that user.
    """

    PATH = "/v1/sessions/revoke"
    SID = "55555555-5555-4555-8555-555555555555"
    OTHER_USER = "99999999-9999-4999-8999-999999999999"
    OTHER_SID = "66666666-6666-4666-8666-666666666666"
    two_tenants = True

    def setUp(self) -> None:
        super().setUp()
        keycloak = self.stack.keycloak
        # SUBJECT is a member of kiraci1 (base setup). OTHER_USER is a member of kiraci2 only.
        other_org = {"id": "o-kiraci2", "name": "kiraci2", "alias": "kiraci2"}
        keycloak.add_user(keycloak_user(subject=self.OTHER_USER, email="ikinci@example.test"), [other_org])
        keycloak.add_session(SUBJECT, self.SID)
        keycloak.add_session(self.OTHER_USER, self.OTHER_SID)

    def revoke(self, payload: object = None, token: str = SESSION_TOKEN) -> tuple[int, object]:
        body = {"sid": self.SID, "subject": SUBJECT} if payload is None else payload
        return self.post_json(self.PATH, body, token)

    def test_tenant_ends_the_session_of_its_own_member(self) -> None:
        with self.assertLogs("identity_sync", level="INFO") as logs:
            reply = self.revoke()

        self.assertEqual(reply, (200, {"sid": self.SID, "revoked": True}))
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [])
        self.assertEqual(self.stack.keycloak.sessions[self.OTHER_USER], [self.OTHER_SID])
        audit = "\n".join(logs.output)
        self.assertIn("operation=revoke_session", audit)
        self.assertIn("site-kiraci1-service", audit)

    def test_closed_session_also_gets_200(self) -> None:
        # Repeatable: the same request twice gives the same answer.
        self.assertEqual(self.revoke()[0], 200)

        self.assertEqual(self.revoke(), (200, {"sid": self.SID, "revoked": True}))

    def test_other_tenant_cannot_end_the_session(self) -> None:
        # kiraci2 knows the session id and the user id. The user is not a member of kiraci2.
        reply = self.revoke(token=OTHER_SITE_TOKEN)

        self.assertEqual(reply, (403, {"error": "forbidden"}))
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [self.SID])

    def test_tenant_cannot_end_a_session_of_another_user_by_naming_its_own_member(self) -> None:
        # kiraci1 sends the session id of kiraci2's user together with its own member's id.
        # The session does not belong to that member, so it is not deleted.
        status, _body = self.revoke({"sid": self.OTHER_SID, "subject": SUBJECT})

        self.assertEqual(status, 200)
        self.assertEqual(self.stack.keycloak.sessions[self.OTHER_USER], [self.OTHER_SID])
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [self.SID])

    def test_tenant_cannot_name_a_user_of_another_tenant(self) -> None:
        reply = self.revoke({"sid": self.OTHER_SID, "subject": self.OTHER_USER})

        self.assertEqual(reply, (403, {"error": "forbidden"}))
        self.assertEqual(self.stack.keycloak.sessions[self.OTHER_USER], [self.OTHER_SID])

    def test_unknown_user_is_forbidden(self) -> None:
        self.assertEqual(self.revoke({"sid": self.SID, "subject": "yok-boyle-kullanici"}), (403, {"error": "forbidden"}))
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [self.SID])

    def test_site_client_without_a_configured_tenant_is_forbidden(self) -> None:
        # The client is in the session list but no tenant in the settings belongs to it.
        import dataclasses

        self.stack.app.settings = dataclasses.replace(self.stack.app.settings, tenants=self.stack.app.settings.tenants[:1])
        self.start_server(fake_verifier)

        self.assertEqual(self.revoke({"sid": self.OTHER_SID, "subject": self.OTHER_USER}, OTHER_SITE_TOKEN)[0], 403)
        self.assertEqual(self.stack.keycloak.sessions[self.OTHER_USER], [self.OTHER_SID])

    def test_only_a_site_client_may_call(self) -> None:
        for token in (PREVIEW_TOKEN, EXECUTE_TOKEN, PRESS_TOKEN, "stranger-token"):
            with self.subTest(token=token):
                self.assertEqual(self.revoke(token=token), (403, {"error": "forbidden"}))
        self.assertEqual(self.call("POST", self.PATH, b'{"sid": "x", "subject": "y"}')[0], 401)
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [self.SID])

    def test_site_client_cannot_use_the_other_endpoints(self) -> None:
        for method, path, body in ServiceTokenTest.PROTECTED:
            with self.subTest(path=path):
                status, _reply = self.call(method, path, body, self.bearer(SESSION_TOKEN))
                self.assertEqual(status, 403)

    def test_bad_request_bodies(self) -> None:
        good = {"sid": self.SID, "subject": SUBJECT}
        for payload in (
            {},
            {"sid": self.SID},
            {"subject": SUBJECT},
            {**good, "sid": ""},
            {**good, "sid": ".."},
            {**good, "sid": 5},
            {**good, "subject": "a/b"},
            {**good, "user": "x"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.revoke(payload), (400, {"error": "bad_request"}))
        self.assertEqual(self.keycloak_writes(), [])

    def test_keycloak_failure_is_an_upstream_failure(self) -> None:
        kc = self.stack.keycloak
        kc.on("DELETE", f"{kc.admin}/sessions/{self.SID}", (500, None))

        self.assertEqual(self.revoke(), (502, {"error": "upstream_failed"}))


class AccountDeletionEndpointTest(ServerCase):
    """POST /v1/account-deletions (docs/sozlesmeler.md, section 7; PROJE-KAYDI.md, O-27).

    Only Press calls it, after it re-authenticated the customer in Keycloak.
    """

    PATH = "/v1/account-deletions"

    def setUp(self) -> None:
        super().setUp()
        issuer = self.stack.issuer
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID, api_keys=1)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        self.stack.tenant.installations[(issuer, SUBJECT)] = ["phone-1"]

    def body(self, **changes: object) -> dict[str, object]:
        return {"issuer": self.stack.issuer, "subject": SUBJECT, "reauthenticated_at": NOW - 10, **changes}

    def request(self, token: str = PRESS_TOKEN, **changes: object) -> tuple[int, object]:
        return self.post_json(self.PATH, self.body(**changes), token)

    def nothing_written(self) -> None:
        self.assertEqual(self.downstream_writes() + self.keycloak_writes(), [])
        self.assertIn(SUBJECT, self.stack.keycloak.users)

    def test_press_request_deletes_the_account(self) -> None:
        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, body = self.request()

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "processed")
        self.assertEqual(body["actions"][0], "keycloak.disable_user")
        self.assertEqual(body["actions"][-1], "keycloak.delete_user")
        issuer = self.stack.issuer
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        self.assertFalse(self.stack.press.user_of(issuer, SUBJECT)["enabled"])
        self.assertTrue(self.stack.tenant.user_of(issuer, SUBJECT)["anonymized"])
        self.assertNotIn((issuer, SUBJECT), self.stack.tenant.installations)
        audit = "\n".join(logs.output)
        self.assertIn("operation=delete_account", audit)
        self.assertIn("press-service", audit)
        self.assertIn("outcome=processed", audit)
        # The log names the request, not the person.
        self.assertNotIn("example.test", audit)
        self.assertNotIn(SUBJECT, audit)

    def test_request_id_does_not_reveal_the_user(self) -> None:
        _status, body = self.request()

        self.assertRegex(body["request_id"], r"^del-[0-9a-f]{40}$")
        self.assertNotIn(SUBJECT, json.dumps(body))

    def test_old_reauthentication_is_refused(self) -> None:
        # Press re-authenticated the customer more than 300 seconds ago.
        for age in (301, 3600):
            with self.subTest(age=age):
                reply = self.request(reauthenticated_at=NOW - age)
                self.assertEqual(reply, (403, {"error": "reauthentication_required"}))
        self.nothing_written()

    def test_reauthentication_at_the_edge_is_accepted(self) -> None:
        self.assertEqual(self.request(reauthenticated_at=NOW - 300)[0], 200)

    def test_reauthentication_from_the_future_is_refused(self) -> None:
        self.assertEqual(self.request(reauthenticated_at=NOW + 120), (403, {"error": "reauthentication_required"}))
        self.nothing_written()

    def test_only_press_may_request_a_deletion(self) -> None:
        for token in (PREVIEW_TOKEN, EXECUTE_TOKEN, SESSION_TOKEN, "stranger-token"):
            with self.subTest(token=token):
                self.assertEqual(self.request(token=token), (403, {"error": "forbidden"}))
        self.assertEqual(self.call("POST", self.PATH, b"{}")[0], 401)
        self.nothing_written()

    def test_press_cannot_use_the_other_endpoints(self) -> None:
        for method, path, body in ServiceTokenTest.PROTECTED:
            with self.subTest(path=path):
                self.assertEqual(self.call(method, path, body, self.bearer(PRESS_TOKEN))[0], 403)

    def test_bad_requests(self) -> None:
        for payload in (
            {},
            {"issuer": self.stack.issuer, "subject": SUBJECT},
            self.body(issuer="http://baska.example.test/realms/platform"),
            self.body(subject=".."),
            self.body(subject=5),
            self.body(reauthenticated_at="simdi"),
            self.body(reauthenticated_at=True),
            self.body(reauthenticated_at=1.5),
            self.body(approval_id="onay-1"),
            self.body(dry_run=True),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.post_json(self.PATH, payload, PRESS_TOKEN), (400, {"error": "bad_request"}))
        self.nothing_written()

    def test_same_account_twice_is_one_job(self) -> None:
        first = self.request()[1]

        status, second = self.request(reauthenticated_at=NOW - 5)

        self.assertEqual((status, second["status"]), (200, "duplicate"))
        self.assertEqual(second["request_id"], first["request_id"])

    def test_failed_step_queues_the_request_and_a_resend_resumes_it(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))

        status, body = self.request()

        self.assertEqual((status, body["status"]), (200, "dead_lettered"))
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        _status, listing = self.call("GET", "/v1/dead-letters", None, self.bearer(PREVIEW_TOKEN))
        (letter,) = listing["dead_letters"]
        self.assertEqual((letter["event"]["kind"], letter["event"]["type"]), ("request", "ACCOUNT_DELETION"))
        self.assertEqual(letter["event"]["id"], body["request_id"])

        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, DONE)
        revokes = len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS))
        status, body = self.request()

        self.assertEqual((status, body["status"]), (200, "processed"))
        self.assertEqual(body["actions"], ["tenant.anonymize_user", "keycloak.delete_user"])
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)), revokes)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)

    def test_queued_job_never_shows_the_account_id_over_http(self) -> None:
        # A preview client can list the queue and preview the retry. It must not learn who it is.
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        _status, body = self.request()
        bearer = self.bearer(PREVIEW_TOKEN)

        _s, listing = self.call("GET", "/v1/dead-letters", None, bearer)
        _s, preview = self.post_json("/v1/dead-letters/replay", {"dry_run": True}, PREVIEW_TOKEN)

        for reply in (listing, preview):
            self.assertNotIn(SUBJECT, json.dumps(reply))
            self.assertIn(body["request_id"], json.dumps(reply))
        operations = [p["operation"] for p in preview["results"][0]["previews"]]
        self.assertEqual(operations, ["tenant.anonymize_user", "keycloak.delete_user"])

    def test_queued_delete_event_preview_hides_the_account_when_reads_differ(self) -> None:
        # The delete event is in the queue because Keycloak could not be read. During the retry
        # preview the first read fails again and a later read says the user is gone.
        keycloak = self.stack.keycloak
        keycloak.remove_user(SUBJECT)
        left = [99]

        def read(_req: fakes.Recorded) -> fakes.Reply:
            if left[0] > 0:
                left[0] -= 1
                return 500, None
            return 404, {"error": "User not found"}

        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", read)
        deleted = {"id": "e-del-2", "kind": "admin", "type": "USER_DELETE", "realm": "platform", "time": 1, "user_id": SUBJECT}
        status, reply = self.post_event(deleted)
        self.assertEqual((status, reply["status"]), (202, "dead_lettered"))
        self.assertEqual(self.downstream_writes(), [])

        for failures in (3, 1, 0):
            with self.subTest(failures=failures):
                left[0] = failures
                status, preview = self.post_json("/v1/dead-letters/replay", {"dry_run": True}, PREVIEW_TOKEN)
                self.assertEqual(status, 200)
                self.assertNotIn(SUBJECT, json.dumps(preview))
        self.assertEqual(self.downstream_writes(), [])

    def test_keycloak_delete_event_after_the_press_request_is_the_same_job(self) -> None:
        # Both real entry paths in one test: the Press request, then the event its last step causes.
        _status, body = self.request()
        self.assertEqual(body["status"], "processed")
        writes = len(self.downstream_writes())
        deleted = {"id": "e-del-1", "kind": "admin", "type": "USER_DELETE", "realm": "platform", "time": 1, "user_id": SUBJECT}

        status, reply = self.post_event(deleted)

        self.assertEqual((status, reply["status"]), (202, "duplicate"))
        self.assertEqual(len(self.downstream_writes()), writes)

    def test_request_is_on_record_before_the_first_write(self) -> None:
        # The process dies during the first step. The request must not be lost.
        keycloak = self.stack.app.keycloak
        original = keycloak.disable_user

        def die(_subject: str) -> None:
            raise KeyboardInterrupt

        keycloak.disable_user = die
        try:
            self.request()
        except Exception:  # the dropped connection reaches the client as an error
            pass
        keycloak.disable_user = original
        self.start_server(fake_verifier)

        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.event.type, "ACCOUNT_DELETION")

    def test_deletion_cannot_be_injected_through_the_event_endpoint(self) -> None:
        # The event endpoint takes Keycloak events only.
        forged = {"id": "x-1", "kind": "request", "type": "ACCOUNT_DELETION", "realm": "platform", "time": 1, "user_id": SUBJECT}

        self.assertEqual(self.post_event(forged), (400, {"error": "bad_request"}))
        self.assertIn(SUBJECT, self.stack.keycloak.users)


class OperationJournalTest(ServerCase):
    """An invitation writes to Keycloak in three steps. Each step is recorded before it runs."""

    INVITATION = {"email": "davetli@example.test", "first_name": "Deniz", "organization_id": ORG_ID}

    def setUp(self) -> None:
        super().setUp()
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, []))
        kc.on("POST", f"{kc.admin}/users", (201, None, {"Location": f"{kc.url}{kc.admin}/users/yeni-kullanici"}))
        kc.on("POST", f"{kc.admin}/organizations/{ORG_ID}/members", (201, None))
        self.email_path = f"{kc.admin}/users/yeni-kullanici/execute-actions-email"
        kc.on("PUT", self.email_path, (204, None))

    def invite(self, approval_id: str = "onay-d1") -> tuple[int, object]:
        _status, preview = self.post_json("/v1/invitations", {**self.INVITATION, "dry_run": True})
        execute = {**self.INVITATION, "dry_run": False, "preview_digest": preview["preview_digest"]}
        return self.post_json("/v1/invitations", {**execute, "approval_id": approval_id})

    def operations(self, token: str = PREVIEW_TOKEN) -> list[dict[str, object]]:
        status, body = self.call("GET", "/v1/operations", None, self.bearer(token))
        self.assertEqual(status, 200)
        return body["operations"]

    def test_finished_invitation_leaves_no_open_operation(self) -> None:
        self.assertEqual(self.invite()[0], 200)
        self.assertEqual(self.operations(), [])

    def test_approval_and_journal_are_written_together(self) -> None:
        # A crash right after the approval is consumed must leave the operation on record.
        store = self.stack.app.store
        original = self.stack.app.keycloak.invite_user
        calls = {"count": 0}

        def die_on_execute(*args, **kwargs):
            calls["count"] += 1
            if not kwargs.get("dry_run"):
                raise KeyboardInterrupt
            return original(*args, **kwargs)

        self.stack.app.keycloak.invite_user = die_on_execute
        try:
            self.invite("onay-d7")
        except Exception:  # the dropped connection reaches the client as an error
            pass
        self.stack.app.keycloak.invite_user = original
        self.start_server(fake_verifier)

        (operation,) = store.operations()
        self.assertEqual((operation["operation_id"], operation["state"]), ("onay-d7", "unknown"))
        self.assertEqual([step["status"] for step in operation["steps"]], ["pending"] * 3)

    def test_failed_step_is_listed_with_the_state_of_every_step(self) -> None:
        self.stack.keycloak.on("PUT", self.email_path, (500, None))

        self.assertEqual(self.invite()[0], 502)

        (operation,) = self.operations()
        self.assertEqual((operation["operation_id"], operation["operation"]), ("onay-d1", "invite_user"))
        self.assertEqual((operation["state"], operation["subject"]), ("failed", "yeni-kullanici"))
        self.assertEqual(
            [(s["step"], s["status"]) for s in operation["steps"]],
            [
                ("keycloak.create_user", "done"),
                ("keycloak.add_organization_member", "done"),
                ("keycloak.send_execute_actions_email", "failed"),
            ],
        )
        self.assertNotIn("example.test", json.dumps(operation))

    def test_dropped_connection_leaves_the_step_unknown(self) -> None:
        # Keycloak took the e-mail request, then the connection died. Nobody knows if the e-mail went out.
        self.stack.keycloak.on("PUT", self.email_path, fakes.DROP)

        self.assertEqual(self.invite()[0], 502)

        (operation,) = self.operations()
        self.assertEqual(operation["state"], "unknown")
        self.assertEqual(operation["steps"][-1]["status"], "unknown")

    def test_human_resolves_an_open_operation_through_the_approval_layer(self) -> None:
        self.stack.keycloak.on("PUT", self.email_path, (500, None))
        self.invite()
        path = "/v1/operations/onay-d1/resolve"

        self.assertEqual(self.post_json(path, {"resolution": "completed"}, PREVIEW_TOKEN), (403, {"error": "forbidden"}))
        self.assertEqual(len(self.operations()), 1)
        self.assertEqual(self.post_json(path, {"resolution": "belki"}), (400, {"error": "bad_request"}))

        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, body = self.post_json(path, {"resolution": "completed"})

        self.assertEqual((status, body), (200, {"operation_id": "onay-d1", "state": "resolved", "resolution": "completed"}))
        self.assertEqual(self.operations(), [])
        self.assertIn("resolve_operation", "\n".join(logs.output))
        self.assertEqual(self.post_json(path, {"resolution": "completed"}), (404, {"error": "not_found"}))

    def test_unknown_operation_id_is_not_found(self) -> None:
        self.assertEqual(self.post_json("/v1/operations/yok/resolve", {"resolution": "abandoned"}), (404, {"error": "not_found"}))
        self.assertEqual(self.post_json("/v1/operations/../resolve", {"resolution": "abandoned"})[0], 404)

    def test_operations_need_a_service_token(self) -> None:
        self.assertEqual(self.call("GET", "/v1/operations")[0], 401)
        self.assertEqual(self.call("POST", "/v1/operations/onay-d1/resolve", b"{}")[0], 401)


class BatchRefusalTest(ServerCase):
    def test_one_changed_event_gets_409_and_nothing_is_written(self) -> None:
        other = "99999999-9999-4999-8999-999999999999"
        org = {"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}
        self.stack.keycloak.add_user(keycloak_user(subject=other, email="ikinci@example.test"), [org])
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.post_event()
        self.post_event({**EVENT, "id": "e-2", "user_id": other})
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, DONE)
        _status, preview = self.post_json("/v1/dead-letters/replay", {"dry_run": True})
        self.stack.keycloak.add_user(keycloak_user(subject=other, email="degisti@example.test"), [org])
        writes = len(self.downstream_writes())
        execute = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-t1"}

        self.assertEqual(self.post_json("/v1/dead-letters/replay", execute), (409, {"error": "preview_changed"}))
        self.assertEqual(len(self.downstream_writes()), writes)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 2)


class DeadLetterEndpointTest(ServerCase):
    def test_list_shows_waiting_events(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.post_event()

        status, body = self.call("GET", "/v1/dead-letters", None, self.bearer(PREVIEW_TOKEN))

        self.assertEqual(status, 200)
        (letter,) = body["dead_letters"]
        self.assertEqual(letter["event"]["id"], "e-1")
        self.assertEqual(letter["error"], "tenant.provision kiraci1: HTTP 503")
        self.assertEqual((letter["attempts"], letter["state"]), (1, "failed"))


class ReconcileEndpointTest(ServerCase):
    """POST /v1/reconcile: the HTTP side of the `reconcile` command (D-9)."""

    PATH = "/v1/reconcile"
    CLOSED = "closed-1"

    def setUp(self) -> None:
        super().setUp()
        # Drift: CLOSED is disabled in Keycloak but still enabled on Press and on the tenant.
        keycloak, issuer = self.stack.keycloak, self.stack.issuer
        org = {"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}
        keycloak.add_user(keycloak_user(subject=self.CLOSED, email="closed@example.test", enabled=False), [org])
        keycloak.serve_directory()
        self.stack.press.seed_member(issuer, self.CLOSED, "closed@example.test", ORG_ID, api_keys=1)
        self.stack.tenant.seed_user(issuer, self.CLOSED, "closed@example.test")
        # The user from the base setup is in sync.
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")

    def preview(self, token: str = PREVIEW_TOKEN) -> dict[str, object]:
        status, body = self.post_json(self.PATH, {"dry_run": True}, token)
        self.assertEqual(status, 200)
        return body

    def execute(self, digest: object, token: str = EXECUTE_TOKEN, approval_id: str = "onay-m1"):
        return self.post_json(self.PATH, {"dry_run": False, "preview_digest": digest, "approval_id": approval_id}, token)

    def test_agent_gets_the_report_and_nothing_is_written(self) -> None:
        body = self.preview()

        self.assertEqual(body["count"], 2)
        self.assertEqual(
            body["differences"],
            [
                {"target": "press", "subject": self.CLOSED, "kind": "closed_in_keycloak"},
                {"target": "kiraci1", "subject": self.CLOSED, "kind": "closed_in_keycloak"},
            ],
        )
        self.assertEqual(
            [p["operation"] for p in body["previews"]],
            ["press.remove_team_member", "tenant.set_enabled", "tenant.revoke_user_installations"],
        )
        self.assertTrue(all(p["destructive"] for p in body["previews"]))
        self.assertRegex(body["preview_digest"], r"^[0-9a-f]{64}$")
        self.assertNotIn("example.test", json.dumps(body))
        self.assertEqual(self.downstream_writes(), [])

    def test_request_must_state_dry_run(self) -> None:
        for payload in ({}, {"dry_run": "true"}, {"dry_run": False}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post_json(self.PATH, payload), (400, {"error": "bad_request"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_agent_cannot_repair(self) -> None:
        digest = self.preview()["preview_digest"]

        self.assertEqual(self.execute(digest, token=PREVIEW_TOKEN), (403, {"error": "forbidden"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_approval_layer_repairs_the_drift(self) -> None:
        issuer = self.stack.issuer
        digest = self.preview()["preview_digest"]

        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, body = self.execute(digest)

        self.assertEqual(status, 200)
        self.assertEqual(
            [(r["operation"], r["target"], r["status"]) for r in body["results"]],
            [
                ("press.remove_team_member", "press", "done"),
                ("tenant.set_enabled", "kiraci1", "done"),
                ("tenant.revoke_user_installations", "kiraci1", "done"),
            ],
        )
        closed_on_press = self.stack.press.user_of(issuer, self.CLOSED)
        self.assertEqual((closed_on_press["enabled"], closed_on_press["api_keys"]), (False, []))
        self.assertFalse(self.stack.tenant.user_of(issuer, self.CLOSED)["enabled"])
        self.assertTrue(self.stack.tenant.user_of(issuer, SUBJECT)["enabled"])
        audit = "\n".join(logs.output)
        self.assertIn("operation=reconcile", audit)
        self.assertIn("onay-m1", audit)
        self.assertIn("outcome=executed", audit)
        self.assertEqual(self.preview()["count"], 0)

    def test_repair_is_refused_when_the_drift_changed(self) -> None:
        digest = self.preview()["preview_digest"]
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [])
        self.stack.keycloak.serve_directory()

        self.assertEqual(self.execute(digest), (409, {"error": "preview_changed"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_approval_works_once(self) -> None:
        digest = self.preview()["preview_digest"]
        self.assertEqual(self.execute(digest)[0], 200)
        writes = len(self.downstream_writes())

        self.assertEqual(self.execute(self.preview()["preview_digest"]), (409, {"error": "approval_used"}))
        self.assertEqual(len(self.downstream_writes()), writes)

    def test_failed_repair_is_reported_not_hidden(self) -> None:
        digest = self.preview()["preview_digest"]
        self.stack.tenant.on("POST", fakes.TENANT_SET_ENABLED, (403, None))

        status, body = self.execute(digest)

        self.assertEqual(status, 200)
        failed = [r for r in body["results"] if r["status"] == "failed"]
        self.assertEqual([(r["operation"], r["error"]) for r in failed], [("tenant.set_enabled", "tenant.set_enabled kiraci1: HTTP 403")])

    def test_unreachable_keycloak_is_an_upstream_failure(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/organizations", (500, None))

        self.assertEqual(self.post_json(self.PATH, {"dry_run": True}), (502, {"error": "upstream_failed"}))


if __name__ == "__main__":
    unittest.main()


class ListLimitTest(ServerCase):
    """frappe-python-standartlari.md, P-3: a list that can grow has an explicit limit and a stable order."""

    def queue(self, count: int) -> None:
        store = self.stack.app.store
        for number in range(count):
            failed = Event(id=f"e-{number:03d}", kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=SUBJECT)
            store.add_dead_letter(failed, "tenant.provision kiraci1: HTTP 503")

    def ids(self, query: str = "") -> tuple[list[str], object]:
        status, body = self.call("GET", "/v1/dead-letters" + query, None, self.bearer(PREVIEW_TOKEN))
        self.assertEqual(status, 200)
        return [letter["event"]["id"] for letter in body["dead_letters"]], body.get("next_offset")

    def test_dead_letter_list_is_cut_at_the_default_limit(self) -> None:
        self.queue(101)

        ids, next_offset = self.ids()

        self.assertEqual((len(ids), ids[0], next_offset), (100, "e-000", 100))
        self.assertEqual(self.ids("?offset=100"), (["e-100"], None))

    def test_pages_do_not_overlap_and_cover_everything(self) -> None:
        self.queue(7)
        seen: list[str] = []
        offset: object = 0
        while offset is not None:
            ids, offset = self.ids(f"?limit=3&offset={offset}")
            self.assertLessEqual(len(ids), 3)
            seen += ids

        self.assertEqual(seen, [f"e-{number:03d}" for number in range(7)])

    def test_bad_paging_values_are_refused(self) -> None:
        for query in ("?limit=0", "?limit=501", "?limit=abc", "?offset=-1", "?limit=1&limit=2", "?offset=1.5"):
            with self.subTest(query=query):
                status, body = self.call("GET", "/v1/dead-letters" + query, None, self.bearer(PREVIEW_TOKEN))
                self.assertEqual((status, body), (400, {"error": "bad_request"}))

    def test_operation_list_has_the_same_limit(self) -> None:
        store = self.stack.app.store
        for number in range(5):
            store.operation_begin(f"o-{number}", "invite_user", ORG_ID, ["s1"])

        status, body = self.call("GET", "/v1/operations?limit=2", None, self.bearer(PREVIEW_TOKEN))

        self.assertEqual(status, 200)
        self.assertEqual(([o["operation_id"] for o in body["operations"]], body["next_offset"]), (["o-0", "o-1"], 2))
        status, body = self.call("GET", "/v1/operations?limit=2&offset=4", None, self.bearer(PREVIEW_TOKEN))
        self.assertEqual(([o["operation_id"] for o in body["operations"]], body.get("next_offset")), (["o-4"], None))


class RateLimitTest(ServerCase):
    """frappe-python-standartlari.md, G-7: endpoints that need no token limit the number of requests."""

    def setUp(self) -> None:
        super().setUp()
        import dataclasses

        self.stack.app.settings = dataclasses.replace(self.stack.app.settings, rate_limit=5)
        self.start_server(fake_verifier)

    def test_requests_over_the_limit_get_429(self) -> None:
        statuses = [self.call("GET", "/healthz")[0] for _ in range(7)]

        self.assertEqual(statuses, [200] * 5 + [429] * 2)
        self.assertEqual(self.call("GET", "/healthz"), (429, {"error": "rate_limited"}))

    def test_unsigned_events_are_limited_too_and_write_nothing(self) -> None:
        statuses = [self.call("POST", "/v1/events", json.dumps(EVENT).encode("utf-8"))[0] for _ in range(7)]

        self.assertEqual(statuses, [401] * 5 + [429] * 2)
        self.assertEqual(self.downstream_writes(), [])

    def test_limit_opens_again_in_the_next_minute(self) -> None:
        for _ in range(6):
            self.call("GET", "/healthz")
        self.assertEqual(self.call("GET", "/healthz")[0], 429)

        self.now += 61

        self.assertEqual(self.call("GET", "/healthz")[0], 200)

    def test_default_limit_is_generous(self) -> None:
        from identity_sync.config import load_settings

        from .test_config_cli import ConfigTest

        self.assertEqual(load_settings(ConfigTest.ENV).rate_limit, 600)


class RequestLogTest(ServerCase):
    """The request log names the route, never the raw path (frappe-python-standartlari.md, G-15).

    A client may put personal data into a path or a query by mistake. The service refuses
    such a request, and its log must not keep what the client sent.
    """

    PERSONAL = "ayse.ornek@example.test"

    def logged(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, _reply = self.call(method, path, body, headers)
        return status, "\n".join(logs.output)

    def test_unknown_path_is_logged_under_a_fixed_name(self) -> None:
        for path in (
            f"/v1/users/{self.PERSONAL}",
            f"/{self.PERSONAL}",
            f"/v1/dead-letters/{self.PERSONAL}",
            f"/v1/operations/{self.PERSONAL}/resolve",
        ):
            with self.subTest(path=path):
                status, log = self.logged("GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn(self.PERSONAL, log)
                self.assertNotIn("ayse", log)
                self.assertIn("unknown 404", log)

    def test_query_values_are_not_logged(self) -> None:
        status, log = self.logged("GET", f"/v1/dead-letters?email={self.PERSONAL}", None, self.bearer(PREVIEW_TOKEN))

        self.assertEqual(status, 400)
        self.assertNotIn(self.PERSONAL, log)
        self.assertNotIn("email", log)
        self.assertIn("/v1/dead-letters 400", log)

    def test_id_in_a_known_path_is_logged_as_the_route_template(self) -> None:
        status, log = self.logged("POST", "/v1/operations/onay-gizli-17/resolve", b'{"resolution": "abandoned"}', self.bearer())

        self.assertEqual(status, 404)
        self.assertNotIn("onay-gizli-17", log)
        self.assertIn("/v1/operations/{operation_id}/resolve 404", log)

    def test_refused_caller_leaves_nothing_it_sent_in_the_log(self) -> None:
        # A preview client may not resolve an operation. It sends a customer number where the
        # operation id belongs. The refusal is logged, the value it sent is not.
        with self.assertLogs("identity_sync", level="INFO") as logs:
            reply = self.call(
                "POST", "/v1/operations/musteri-48213/resolve", b'{"resolution": "abandoned"}', self.bearer(PREVIEW_TOKEN)
            )

        self.assertEqual(reply, (403, {"error": "forbidden"}))
        # The whole log output of the request: one audit line and one request line.
        self.assertEqual(
            logs.output,
            [
                "WARNING:identity_sync:execute operation=resolve_operation azp=ai-agent outcome=forbidden",
                "INFO:identity_sync:/v1/operations/{operation_id}/resolve 403",
            ],
        )

    def test_no_refusal_logs_a_value_from_the_request(self) -> None:
        # Every endpoint, called by a listed client without the right, with made-up personal
        # values in the body. None of them may reach the log.
        marker = "musteri-48213"
        bodies = (
            ("/v1/reconcile", {"dry_run": False, "preview_digest": "0" * 64, "approval_id": marker}, PREVIEW_TOKEN),
            ("/v1/dead-letters/replay", {"dry_run": False, "preview_digest": "0" * 64, "approval_id": marker}, PREVIEW_TOKEN),
            ("/v1/invitations", {"email": f"{marker}@example.test", "organization_id": marker, "dry_run": True}, PRESS_TOKEN),
            ("/v1/sessions/revoke", {"sid": marker, "subject": marker}, PREVIEW_TOKEN),
            ("/v1/account-deletions", {"issuer": self.stack.issuer, "subject": marker, "reauthenticated_at": NOW}, PREVIEW_TOKEN),
            (f"/v1/operations/{marker}/resolve", {"resolution": "abandoned"}, PREVIEW_TOKEN),
        )
        for path, body, token in bodies:
            with self.subTest(path=path), self.assertLogs("identity_sync", level="INFO") as logs:
                status, _reply = self.post_json(path, body, token)
                self.assertEqual(status, 403)
            self.assertNotIn(marker, "\n".join(logs.output))

    def test_known_routes_are_logged_by_name_and_status(self) -> None:
        self.assertIn("/healthz 200", self.logged("GET", "/healthz")[1])
        self.assertIn("/v1/dead-letters 200", self.logged("GET", "/v1/dead-letters", None, self.bearer(PREVIEW_TOKEN))[1])

    def test_failure_logs_name_the_route_too(self) -> None:
        keycloak = self.stack.keycloak
        keycloak.add_session(SUBJECT, "sid-1")
        keycloak.on("DELETE", f"{keycloak.admin}/sessions/sid-1", (500, None))
        body = json.dumps({"sid": "sid-1", "subject": SUBJECT}).encode()

        status, log = self.logged("POST", f"/v1/sessions/revoke?who={self.PERSONAL}", body, self.bearer(SESSION_TOKEN))

        self.assertEqual(status, 502)
        self.assertIn("upstream failed on /v1/sessions/revoke", log)
        self.assertNotIn(self.PERSONAL, log)

    def test_wrong_method_on_a_known_route_is_logged_by_name(self) -> None:
        status, log = self.logged("DELETE", f"/v1/dead-letters?x={self.PERSONAL}")

        self.assertEqual(status, 405)
        self.assertIn("/v1/dead-letters 405", log)
        self.assertNotIn(self.PERSONAL, log)

    def test_broken_request_line_is_not_logged(self) -> None:
        import socket

        with self.assertLogs("identity_sync", level="INFO") as logs:
            with socket.create_connection(self.httpd.server_address, timeout=5) as raw:
                raw.sendall(f"BOGUS {self.PERSONAL} and more words HTTP/9.9\r\n\r\n".encode("ascii"))
                raw.recv(4096)
            self.call("GET", "/healthz")  # makes sure the first request was handled and logged
        log = "\n".join(logs.output)

        self.assertNotIn(self.PERSONAL, log)
        self.assertNotIn("ayse", log)


class TargetErrorValueTest(ServerCase):
    """A value a target puts into its error reply never reaches the log, a reply or the store.

    The target's error name (`exc_type`) is free text chosen by the target. A plain word passes
    any shape check, and it may be a customer code. The service keeps the HTTP status and, only
    for the names in its own fixed list, the name.
    """

    MARKER = "MUSTERI48213"

    def everything(self, logs) -> str:
        store = "\n".join(self.stack.app.store._db.iterdump())
        _status, queue = self.call("GET", "/v1/dead-letters", None, self.bearer(PREVIEW_TOKEN))
        return "\n".join(logs.output) + store + json.dumps(queue)

    def test_unknown_error_name_from_keycloak_is_dropped(self) -> None:
        keycloak = self.stack.keycloak
        keycloak.add_session(SUBJECT, "sid-1")
        keycloak.on("DELETE", f"{keycloak.admin}/sessions/sid-1", (500, {"exc_type": self.MARKER, "message": self.MARKER}))
        body = {"sid": "sid-1", "subject": SUBJECT}

        with self.assertLogs("identity_sync", level="INFO") as logs:
            reply = self.post_json("/v1/sessions/revoke", body, SESSION_TOKEN)
            text = self.everything(logs)

        self.assertEqual(reply, (502, {"error": "upstream_failed"}))
        self.assertNotIn(self.MARKER, text)
        self.assertIn("upstream failed on /v1/sessions/revoke: HTTP 500", text)

    def test_unknown_error_name_from_a_tenant_is_dropped_everywhere(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (409, {"exc_type": self.MARKER, "exception": self.MARKER}))

        with self.assertLogs("identity_sync", level="INFO") as logs:
            status, reply = self.post_event()
            text = self.everything(logs) + json.dumps(reply)

        self.assertEqual((status, reply["status"]), (202, "dead_lettered"))
        self.assertNotIn(self.MARKER, text)
        (letter,) = self.stack.app.store.dead_letters()
        self.assertIn("tenant.provision kiraci1: HTTP 409", letter.error)

    def test_known_error_name_is_kept_for_the_operator(self) -> None:
        # A name from the target contracts tells the operator what to fix. It is from a fixed list.
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (409, {"exc_type": "EmailMismatch"}))

        self.post_event()

        (letter,) = self.stack.app.store.dead_letters()
        self.assertIn("HTTP 409 EmailMismatch", letter.error)

    def test_only_listed_names_are_ever_kept(self) -> None:
        from identity_sync.httpjson import KNOWN_ERROR_CODES, HttpError

        self.assertIn("IdentityNotFound", KNOWN_ERROR_CODES)
        self.assertEqual(str(HttpError(409, "EmailMismatch")), "HTTP 409 EmailMismatch")
        for name in (self.MARKER, "Musteri48213", "emailmismatch", "EmailMismatch2", ""):
            with self.subTest(name=name):
                error = HttpError(409, name)
                self.assertEqual((error.code, str(error)), (None, "HTTP 409"))
