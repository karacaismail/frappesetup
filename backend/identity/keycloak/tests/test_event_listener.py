"""Event listener fork (decision D-10, option 1; contract section 7 and identity-sync webhookSignature).

Expected values come from the contract: header names, HMAC-SHA256 over
"<timestamp>.<mode>.<raw body>", a timestamp within 300 seconds, Keycloak's own body with realmId.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
import unittest
import uuid

from yardimci import KLASOR, ORNEK_ENV, admin, canli_var_mi, istek, ortam, realm_oku, yonetici_belirteci, safe_detail

LISTENER = KLASOR / "event-listener"
DOCKERFILE = KLASOR / "Dockerfile"
COMPOSE = KLASOR.parents[1] / "dev" / "compose.keycloak.yaml"
UPSTREAM_COMMIT = "5f23e5530db15c9042d8977c46a19758aa0ede97"
SIGNATURE_WINDOW_SECONDS = 300


class EventListenerFileTest(unittest.TestCase):
    def test_license_and_notice_are_kept(self):
        self.assertIn("Apache License", (LISTENER / "LICENSE").read_text(encoding="utf-8")[:200])
        notice = (LISTENER / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("sashyo/keycloak-webhook-listener", notice)
        self.assertIn(UPSTREAM_COMMIT, notice)
        self.assertIn("Apache License, Version 2.0", notice)

    def test_modified_upstream_files_carry_a_notice(self):
        # Apache-2.0 section 4(b): modified files carry a prominent notice.
        source = LISTENER / "src" / "main" / "java" / "au" / "com" / "ais" / "keycloak" / "webhook"
        for name in ("WebhookEventListenerProvider.java", "WebhookEventListenerProviderFactory.java"):
            self.assertIn("Modified by this project", (source / name).read_text(encoding="utf-8")[:400], name)

    def test_image_builds_the_listener_with_tests_and_a_pinned_maven_image(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"(?m)^ARG MAVEN_IMAGE=maven:[^\n]+@sha256:[0-9a-f]{64}$")
        stage = re.search(r"FROM \$\{MAVEN_IMAGE\} AS event-listener-build\n(.*?)\nFROM ",
                          dockerfile, re.S)
        self.assertIsNotNone(stage, "multi-stage Maven build with a digest-pinned image is missing")
        self.assertIn("COPY event-listener/", stage.group(1))
        self.assertIn("mvn", stage.group(1))
        self.assertNotIn("skipTests", stage.group(1))  # the JUnit tests gate the image
        self.assertRegex(dockerfile, r"COPY --from=event-listener-build --chown=1000:0 \S+ /opt/keycloak/providers/")

    def test_realm_sends_events_to_the_webhook_listener(self):
        realm = realm_oku()
        self.assertIn("webhook", realm["eventsListeners"])
        self.assertTrue(realm["eventsEnabled"])
        self.assertTrue(realm["adminEventsEnabled"])
        # The listener never sends the representation. Keycloak need not store it either.
        self.assertFalse(realm["adminEventsDetailsEnabled"])

    def test_listener_settings_come_from_the_environment(self):
        compose = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("KC_SPI_EVENTS_LISTENER__WEBHOOK__URL: ${IDENTITY_SYNC_EVENTS_URL:?}", compose)
        self.assertIn("KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET: ${IDENTITY_SYNC_WEBHOOK_SECRET:?}", compose)
        example = ORNEK_ENV.read_text(encoding="utf-8")
        self.assertRegex(example, r"(?m)^IDENTITY_SYNC_WEBHOOK_SECRET=degistir-")
        self.assertRegex(example, r"(?m)^IDENTITY_SYNC_EVENTS_URL=http://event-sink.localhost:8080/v1/events$")


def _sink_requests() -> list:
    """Requests the sink recorded. An empty list means the sink is up and got nothing yet.

    Standard V-11: a missing sink container or a Docker error raises; it is never read as "no requests",
    or a test that expects no request would pass with the sink down.
    """
    context = os.environ.get("DOCKER_CONTEXT", "colima-factory")
    project = os.environ.get("COMPOSE_PROJECT_NAME", "fs-kimlik-realm")
    # The sink writes the file on its first request; "touch" makes "no request yet" an empty file.
    result = subprocess.run(
        ["docker", "--context", context, "exec", f"{project}-event-sink-1", "sh", "-c",
         "touch /tmp/requests.jsonl && cat /tmp/requests.jsonl"],
        capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"event sink is not readable: {result.stderr.strip()[:200]}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _contract_signature(secret: str, timestamp: str, mode: str, body: bytes) -> str:
    message = f"{timestamp}.{mode}.".encode("ascii") + body
    return "sha256=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


@unittest.skipUnless(canli_var_mi(), "KC_PUBLIC_URL is not set; live Keycloak test skipped")
class EventListenerLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = ortam("KC_PUBLIC_URL")
        cls.secret = ortam("IDENTITY_SYNC_WEBHOOK_SECRET")
        cls.admin_token = yonetici_belirteci()
        cls.realm_id = admin("", cls.admin_token).json()["id"]

    def _wait_for(self, predicate, seconds: float = 20.0) -> list:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            matches = [r for r in _sink_requests() if predicate(r)]
            if matches:
                return matches
            time.sleep(0.5)
        return []

    def test_listener_is_loaded(self):
        info = istek("GET", f"{self.kc}/admin/serverinfo", belirtec=self.admin_token).json()
        self.assertIn("webhook", info["providers"]["eventsListener"]["providers"])

    def test_user_creation_is_sent_signed_with_realm_id(self):
        username = f"event-{uuid.uuid4().hex[:10]}"
        created = admin("/users", self.admin_token, "POST", {
            "username": username, "email": f"{username}@example.test", "enabled": True})
        self.assertEqual(created.durum, 201, safe_detail(created))
        user_id = created.basliklar["Location"].rstrip("/").rsplit("/", 1)[1]
        self.addCleanup(admin, f"/users/{user_id}", self.admin_token, "DELETE")
        sent_after = int(time.time()) - 5

        def is_creation(request):
            body = json.loads(base64.b64decode(request["body"]))
            return body.get("resourcePath") == f"users/{user_id}" and body.get("operationType") == "CREATE"

        matches = self._wait_for(is_creation)
        self.assertEqual(len(matches), 1, "the sink received no single USER CREATE event")
        request = matches[0]
        raw = base64.b64decode(request["body"])
        body = json.loads(raw)

        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"], "/v1/events")  # execute mode: no dry_run parameter
        self.assertEqual(request["content_type"], "application/json")
        self.assertRegex(request["timestamp"], r"^[0-9]{1,12}$")
        self.assertLessEqual(abs(int(request["timestamp"]) - sent_after), SIGNATURE_WINDOW_SECONDS)
        self.assertEqual(request["signature"], _contract_signature(self.secret, request["timestamp"], "execute", raw))
        self.assertNotEqual(request["signature"], _contract_signature(self.secret, request["timestamp"], "preview", raw))

        self.assertEqual(body["realmId"], self.realm_id)
        self.assertNotEqual(body["realmId"], "platform")
        self.assertEqual(body["resourceType"], "USER")
        self.assertIsInstance(body["time"], int)
        self.assertFalse({"representation", "authDetails", "realm", "ipAddress"} & set(body), sorted(body))
        self.assertNotIn(b"example.test", raw)  # no e-mail address leaves Keycloak

    def test_events_the_service_ignores_are_not_sent(self):
        group = f"event-group-{uuid.uuid4().hex[:8]}"
        created = admin("/groups", self.admin_token, "POST", {"name": group})
        self.assertEqual(created.durum, 201, safe_detail(created))
        group_id = created.basliklar["Location"].rstrip("/").rsplit("/", 1)[1]
        self.addCleanup(admin, f"/groups/{group_id}", self.admin_token, "DELETE")
        time.sleep(3)
        groups = [r for r in _sink_requests()
                  if json.loads(base64.b64decode(r["body"])).get("resourceType") == "GROUP"]
        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
