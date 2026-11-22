"""Verify real Keycloak delivery and signature rejection in the shared stack.

Run with PANE_PORT set. The synthetic account remains in the development database.
The successful event is emitted by Keycloak, never posted by this test.
"""

import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import runpy
import sqlite3
import sys
import time
import urllib.parse
import uuid


def request(origin, path, *, method="GET", data=None, token=None, headers=None):
    target = urllib.parse.urlsplit(origin)
    if (
        target.scheme not in ("http", "https")
        or not target.hostname
        or target.username is not None
        or target.query
        or target.fragment
    ):
        raise ValueError("Expected an HTTP or HTTPS service address.")
    if not path.startswith("/") or path.startswith("//") or "#" in path:
        raise ValueError("Expected a service-relative request path.")

    headers = dict(headers or {})
    if token:
        headers["Authorization"] = "Bearer " + token
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    connection_type = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(target.hostname, target.port, timeout=15)
    try:
        connection.request(method, target.path.rstrip("/") + path, body=data, headers=headers)
        with connection.getresponse() as response:
            raw = response.read()
            body = json.loads(raw) if raw and not 300 <= response.status < 400 else None
            return response.status, response.headers, body
    finally:
        connection.close()


def inside():
    from identity_sync.config import load_settings
    from identity_sync.events import from_keycloak, parse_event

    settings = load_settings(os.environ)
    origin = settings.keycloak_base_url
    status, _, auth = request(
        origin, "/realms/master/protocol/openid-connect/token",
        method="POST",
        data=urllib.parse.urlencode(
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": os.environ["KC_BOOTSTRAP_ADMIN_USERNAME"],
                "password": os.environ["KC_BOOTSTRAP_ADMIN_PASSWORD"],
            }
        ).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200, f"Admin authentication returned {status}"
    token = auth["access_token"]
    root = "/admin/realms/platform"
    email = "delivery-" + uuid.uuid4().hex + "@example.test"
    status, headers, _ = request(
        origin, root + "/users",
        method="POST",
        token=token,
        data={
            "username": email,
            "email": email,
            "emailVerified": True,
            "enabled": True,
            "firstName": "Delivery",
            "lastName": "Before",
        },
    )
    assert status == 201, f"User creation returned {status}"
    subject = headers["Location"].rsplit("/", 1)[1]
    user_path = root + "/users/" + urllib.parse.quote(subject, safe="")
    status, _, _ = request(origin, user_path, method="PUT", token=token, data={"lastName": "After"})
    assert status == 204, f"User update returned {status}"
    query = urllib.parse.urlencode({"resourcePath": "users/" + subject, "operationTypes": "UPDATE"})
    deadline = time.monotonic() + 60
    event_id = None
    with sqlite3.connect("file:" + os.environ["IDENTITY_SYNC_DB"] + "?mode=ro", uri=True) as database:
        while time.monotonic() < deadline:
            status, _, events = request(origin, root + "/admin-events?" + query, token=token)
            assert status == 200, f"Admin event lookup returned {status}"
            for payload in events:
                if (
                    payload.get("resourcePath") != "users/" + subject
                    or payload.get("operationType") != "UPDATE"
                ):
                    continue
                event = parse_event(from_keycloak(payload, realm_id=settings.realm_id, realm=settings.realm))
                row = database.execute(
                    "SELECT status FROM processed_events WHERE event_id = ?", (event.id,)
                ).fetchone()
                if row and row[0] == "processed":
                    event_id = event.id
                    break
            if event_id:
                break
            time.sleep(0.5)
        assert event_id, "Keycloak USER_UPDATE was not processed within 60 seconds"
        print(
            json.dumps(
                {"source": "Keycloak", "event": "USER_UPDATE", "event_id": event_id, "status": "processed"}
            ),
            flush=True,
        )
        rejected_id = "rejected-" + uuid.uuid4().hex
        body = json.dumps(
            {
                "id": rejected_id,
                "kind": "admin",
                "type": "USER_UPDATE",
                "realm": "platform",
                "time": int(time.time() * 1000),
                "user_id": subject,
            }
        ).encode()
        for name, timestamp, secret in (
            ("bad_signature", int(time.time()), "incorrect-secret-for-test"),
            ("stale_timestamp", int(time.time()) - 600, os.environ["IDENTITY_SYNC_WEBHOOK_SECRET"]),
        ):
            digest = hmac.new(
                secret.encode(), str(timestamp).encode() + b".execute." + body, hashlib.sha256
            ).hexdigest()
            status, _, reply = request(
                "http://127.0.0.1:6115", "/v1/events",
                method="POST",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Identity-Sync-Timestamp": str(timestamp),
                    "X-Identity-Sync-Signature": "sha256=" + digest,
                },
            )
            assert status == 401 and reply.get("error") == "bad_signature", f"{name} was not rejected"
            print(json.dumps({"case": name, "http_status": status, "status": "rejected"}), flush=True)
        for table in ("processed_events", "dead_letters"):
            assert (
                database.execute(f"SELECT 1 FROM {table} WHERE event_id = ?", (rejected_id,)).fetchone()
                is None
            )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--inside":
        inside()
        return
    stack = runpy.run_path(str(Path(__file__).with_name("stack")))
    environment, engine, compose = stack["setup"]()
    stack["assert_owner"](engine, compose, environment)
    stack["run"](
        [
            *compose,
            "exec",
            "-T",
            "-e",
            "KC_BOOTSTRAP_ADMIN_USERNAME",
            "-e",
            "KC_BOOTSTRAP_ADMIN_PASSWORD",
            "identity-sync",
            "python",
            "-",
            "--inside",
        ],
        environment,
        input=Path(__file__).read_text(),
        text=True,
    )


if __name__ == "__main__":
    main()
