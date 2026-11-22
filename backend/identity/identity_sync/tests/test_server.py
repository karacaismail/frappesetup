"""HTTP uçlarının testleri. İstekler gerçek HTTP yolundan gider (D-6).

Beklenen durum kodlarının kaynağı `contracts/identity_sync.openapi.yaml` dosyasıdır.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import unittest
import urllib.error
import urllib.request

from identity_sync.server import TokenRejected, make_server

from . import fakes
from .fakes import ORG_ID, SUBJECT, WEBHOOK_SECRET, Stack, keycloak_user

GOOD_TOKEN = "good-token"
EVENT = {"id": "e-1", "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 1, "user_id": SUBJECT}


def fake_verifier(token: str) -> dict[str, object]:
    if token != GOOD_TOKEN:
        raise TokenRejected("invalid_signature")
    return {"azp": "press-service", "aud": "identity-sync"}


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class ServerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)
        self.httpd = make_server(self.stack.app, fake_verifier, host="127.0.0.1", port=0)
        thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.stack.keycloak.add_user(keycloak_user(), [{"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}])

    def call(
        self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> tuple[int, object]:
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def post_event(self, payload: object = EVENT, signature: str | None = None, path: str = "/v1/events"):
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        headers["X-Identity-Sync-Signature"] = sign(body) if signature is None else signature
        return self.call("POST", path, body, headers)

    def bearer(self, token: str = GOOD_TOKEN) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def downstream_writes(self) -> list[fakes.Recorded]:
        return self.stack.press.writes() + self.stack.tenant.writes()


class HealthTest(ServerCase):
    def test_health_needs_no_credentials(self) -> None:
        self.assertEqual(self.call("GET", "/healthz"), (200, {"status": "ok"}))

    def test_unknown_path(self) -> None:
        self.assertEqual(self.call("GET", "/yok"), (404, {"error": "not_found"}))

    def test_wrong_method(self) -> None:
        self.assertEqual(self.call("GET", "/v1/events"), (405, {"error": "method_not_allowed"}))


class EventEndpointTest(ServerCase):
    def test_signed_event_is_processed(self) -> None:
        status, body = self.post_event()

        self.assertEqual(status, 202)
        self.assertEqual(body, {"status": "processed", "actions": ["press.ensure_team", "tenant.provision"]})
        self.assertEqual(len(self.downstream_writes()), 2)

    def test_second_delivery_is_a_duplicate(self) -> None:
        self.post_event()

        status, body = self.post_event()

        self.assertEqual((status, body["status"]), (202, "duplicate"))
        self.assertEqual(len(self.downstream_writes()), 2)

    def test_missing_signature_is_rejected(self) -> None:
        body = json.dumps(EVENT).encode()

        status, reply = self.call("POST", "/v1/events", body, {"Content-Type": "application/json"})

        self.assertEqual((status, reply), (401, {"error": "bad_signature"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_wrong_signature_is_rejected(self) -> None:
        wrong = sign(json.dumps(EVENT).encode(), "baska-anahtar")

        status, reply = self.post_event(signature=wrong)

        self.assertEqual((status, reply), (401, {"error": "bad_signature"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_signature_of_other_body_is_rejected(self) -> None:
        other = sign(json.dumps({**EVENT, "id": "e-2"}).encode())

        status, _reply = self.post_event(signature=other)

        self.assertEqual(status, 401)

    def test_service_token_does_not_open_event_endpoint(self) -> None:
        body = json.dumps(EVENT).encode()

        status, _reply = self.call("POST", "/v1/events", body, self.bearer())

        self.assertEqual(status, 401)

    def test_invalid_json_is_bad_request(self) -> None:
        body = b"{bozuk"
        status, reply = self.call("POST", "/v1/events", body, {"X-Identity-Sync-Signature": sign(body)})

        self.assertEqual((status, reply), (400, {"error": "bad_request"}))

    def test_missing_field_is_bad_request(self) -> None:
        status, reply = self.post_event({"id": "e-1", "kind": "user"})

        self.assertEqual((status, reply), (400, {"error": "bad_request"}))

    def test_large_body_is_rejected_before_processing(self) -> None:
        payload = {**EVENT, "dolgu": "x" * 70000}

        status, reply = self.post_event(payload)

        self.assertEqual((status, reply), (413, {"error": "too_large"}))
        self.assertEqual(self.downstream_writes(), [])

    def test_keycloak_native_event_is_accepted(self) -> None:
        native = {"id": "k-1", "time": 1, "type": "VERIFY_EMAIL", "realmId": "platform", "userId": SUBJECT}

        status, body = self.post_event(native)

        self.assertEqual((status, body["status"]), (202, "processed"))

    def test_failed_delivery_is_accepted_and_queued(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))

        status, body = self.post_event()

        self.assertEqual((status, body["status"]), (202, "dead_lettered"))

    def test_dry_run_returns_preview_and_writes_nothing(self) -> None:
        status, body = self.post_event(path="/v1/events?dry_run=true")

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "preview")
        self.assertEqual([p["operation"] for p in body["previews"]], ["press.ensure_team", "tenant.provision"])
        self.assertEqual([p["destructive"] for p in body["previews"]], [False, False])
        self.assertEqual(self.downstream_writes(), [])


class ServiceTokenTest(ServerCase):
    PROTECTED = (
        ("POST", "/v1/reconcile", b"{}"),
        ("GET", "/v1/dead-letters", None),
        ("POST", "/v1/dead-letters/replay", b'{"dry_run": false}'),
        ("POST", "/v1/invitations", b'{"email": "a@example.test", "organization_id": "o", "dry_run": false}'),
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
        self.assertEqual(self.downstream_writes(), [])
        self.assertEqual([r for r in self.stack.keycloak.requests if r.method != "GET"], [])

    def test_webhook_signature_does_not_open_protected_endpoints(self) -> None:
        body = b'{"dry_run": false}'

        status, _reply = self.call(
            "POST", "/v1/dead-letters/replay", body, {"X-Identity-Sync-Signature": sign(body)}
        )

        self.assertEqual(status, 401)

    def test_request_with_cookie_and_token_is_rejected(self) -> None:
        headers = {**self.bearer(), "Cookie": "sid=abc"}

        status, _reply = self.call("GET", "/v1/dead-letters", None, headers)

        self.assertEqual(status, 401)


class DeadLetterEndpointTest(ServerCase):
    def fail_once(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.post_event()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (200, {"message": {"ok": True}}))

    def test_list_shows_waiting_events(self) -> None:
        self.fail_once()

        status, body = self.call("GET", "/v1/dead-letters", None, self.bearer())

        self.assertEqual(status, 200)
        (letter,) = body["dead_letters"]
        self.assertEqual(letter["event"]["id"], "e-1")
        self.assertEqual(letter["error"], "tenant.provision kiraci1: HTTP 503")
        self.assertEqual(letter["attempts"], 1)

    def test_replay_needs_explicit_dry_run_choice(self) -> None:
        self.fail_once()

        status, reply = self.call("POST", "/v1/dead-letters/replay", b"{}", self.bearer())

        self.assertEqual((status, reply), (400, {"error": "bad_request"}))
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

    def test_replay_dry_run_shows_plan(self) -> None:
        self.fail_once()
        writes_before = len(self.downstream_writes())

        status, body = self.call("POST", "/v1/dead-letters/replay", b'{"dry_run": true}', self.bearer())

        self.assertEqual(status, 200)
        (result,) = body["results"]
        self.assertEqual((result["event_id"], result["status"]), ("e-1", "preview"))
        self.assertEqual(len(self.downstream_writes()), writes_before)

    def test_replay_runs_waiting_events(self) -> None:
        self.fail_once()

        status, body = self.call("POST", "/v1/dead-letters/replay", b'{"dry_run": false}', self.bearer())

        self.assertEqual(status, 200)
        self.assertEqual(body["results"][0]["status"], "processed")
        self.assertEqual(self.stack.app.store.dead_letters(), [])


class ReconcileEndpointTest(ServerCase):
    def test_reports_differences_without_writing(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/organizations", lambda r: (200, [] if r.query["first"] != ["0"] else [
            {"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}]))
        kc.on("GET", f"{kc.admin}/organizations/{ORG_ID}/members", lambda r: (200, [] if r.query["first"] != ["0"] else [
            keycloak_user()]))
        self.stack.press.on("GET", fakes.PRESS_LIST, (200, {"message": []}))
        self.stack.tenant.on(
            "GET",
            fakes.TENANT_LIST,
            (200, {"message": [
                {"issuer": self.stack.issuer, "subject": SUBJECT, "email": "eski@example.test", "enabled": True}
            ]}),
        )

        status, body = self.call("POST", "/v1/reconcile", b"{}", self.bearer())

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


class InvitationEndpointTest(ServerCase):
    def test_dry_run_previews_invitation(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, []))
        body = json.dumps(
            {"email": "davetli@example.test", "first_name": "Deniz", "organization_id": ORG_ID, "dry_run": True}
        ).encode()

        status, reply = self.call("POST", "/v1/invitations", body, self.bearer())

        self.assertEqual(status, 200)
        self.assertIsNone(reply["subject"])
        self.assertEqual(
            [p["operation"] for p in reply["previews"]],
            ["keycloak.create_user", "keycloak.add_organization_member", "keycloak.send_execute_actions_email"],
        )
        self.assertEqual([r for r in kc.requests if r.method != "GET" and "/admin/" in r.path], [])

    def test_missing_dry_run_is_bad_request(self) -> None:
        body = json.dumps({"email": "davetli@example.test", "organization_id": ORG_ID}).encode()

        status, reply = self.call("POST", "/v1/invitations", body, self.bearer())

        self.assertEqual((status, reply), (400, {"error": "bad_request"}))

    def test_bad_email_is_bad_request(self) -> None:
        body = json.dumps({"email": "eposta-degil", "organization_id": ORG_ID, "dry_run": True}).encode()

        status, _reply = self.call("POST", "/v1/invitations", body, self.bearer())

        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
