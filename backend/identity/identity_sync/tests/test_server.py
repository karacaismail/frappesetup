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

from identity_sync.server import TokenRejected, make_server

from . import fakes
from .fakes import DONE, ORG_ID, REALM_ID, SUBJECT, WEBHOOK_SECRET, Stack, keycloak_user

NOW = 1_795_000_000
PREVIEW_TOKEN = "preview-token"  # yapay zekâ aracısının belirteci: yalnız okur ve önizler
EXECUTE_TOKEN = "execute-token"  # onay katmanının belirteci: yürütebilir
EVENT = {"id": "e-1", "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 1, "user_id": SUBJECT}
ALL_ACTIONS = ["press.ensure_team", "tenant.provision", "tenant.change_email"]


def fake_verifier(token: str) -> dict[str, object]:
    azp = {PREVIEW_TOKEN: "ai-agent", EXECUTE_TOKEN: "approval-service", "stranger-token": "baska-istemci"}.get(token)
    if azp is None:
        raise TokenRejected("invalid_signature")
    return {"azp": azp, "aud": "identity-sync"}


def sign(body: bytes, timestamp: int, mode: str = "execute", secret: str = WEBHOOK_SECRET) -> str:
    message = f"{timestamp}.{mode}.".encode() + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class ServerCase(unittest.TestCase):
    request_timeout = 0.5

    def setUp(self) -> None:
        self.stack = Stack()
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
        ("POST", "/v1/reconcile", b"{}"),
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
    def test_reports_differences_without_writing(self) -> None:
        kc = self.stack.keycloak
        org = {"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}
        kc.on("GET", f"{kc.admin}/organizations", lambda r: (200, [org] if r.query["first"] == ["0"] else []))
        kc.on(
            "GET",
            f"{kc.admin}/organizations/{ORG_ID}/members",
            lambda r: (200, [keycloak_user()] if r.query["first"] == ["0"] else []),
        )
        self.stack.press.on("GET", fakes.PRESS_LIST, (200, {"message": []}))
        row = {"issuer": self.stack.issuer, "subject": SUBJECT, "email": "eski@example.test", "enabled": True}
        self.stack.tenant.on("GET", fakes.TENANT_LIST, (200, {"message": [row]}))

        status, body = self.call("POST", "/v1/reconcile", b"{}", self.bearer(PREVIEW_TOKEN))

        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {
                "count": 2,
                "differences": [
                    {"target": "press", "subject": SUBJECT, "kind": "missing"},
                    {"target": "kiraci1", "subject": SUBJECT, "kind": "email_mismatch"},
                ],
            },
        )
        self.assertEqual(self.downstream_writes(), [])


if __name__ == "__main__":
    unittest.main()
