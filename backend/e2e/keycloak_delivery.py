"""Verify real Keycloak delivery and signature rejection in the shared stack.

Run with PANE_PORT set. The synthetic account remains in the development database.
The successful event is emitted by Keycloak, never posted by this test.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import runpy
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


DEFAULT_PORTS = {"http": 80, "https": 443}
RECEIVER = "http://127.0.0.1:6115"
USER_PATH = re.compile(r"/admin/realms/platform/users/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})")

# Only plain HTTP(S) handlers: no proxy, no file or FTP scheme, and no redirect
# handler. A 3xx reply becomes an HTTPError, so credentials never move on.
OPENER = urllib.request.OpenerDirector()
for handler in (
    urllib.request.HTTPHandler(),
    urllib.request.HTTPSHandler(),
    urllib.request.HTTPDefaultErrorHandler(),
    urllib.request.HTTPErrorProcessor(),
):
    OPENER.add_handler(handler)


def origin(url):
    """Return scheme, host and port of an http(s) URL without user info."""
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
        parts = parts._replace(netloc="")
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname or parts.username is not None:
        raise ValueError("The Keycloak URL must use http or https and must not contain credentials.")
    return f"{parts.scheme}://{parts.hostname.lower()}:{port or DEFAULT_PORTS[parts.scheme]}"


def user_id(location):
    match = USER_PATH.fullmatch(urllib.parse.urlsplit(location).path)
    if not match or urllib.parse.urlsplit(location).query:
        raise ValueError("Keycloak returned an unexpected user ID location.")
    return match.group(1)


def request(url, *, origins, method="GET", data=None, token=None, headers=None):
    """Send one request to an allowed origin and refuse any redirect."""
    try:
        allowed = origin(url) in {origin(value) for value in origins}
    except ValueError:
        allowed = False
    if not allowed:
        raise ValueError("The request URL is not allowed.")
    headers = dict(headers or {})
    if token:
        headers["Authorization"] = "Bearer " + token
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    call = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        response = OPENER.open(call, timeout=15)
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            error.close()
            raise ValueError("The server sent a redirect. Redirects are not followed.") from None
        response = error
    with response:
        raw = response.read()
        return response.status, response.headers, json.loads(raw) if raw else None


def inside():
    from identity_sync.config import load_settings
    from identity_sync.events import from_keycloak, parse_event

    settings = load_settings(os.environ)
    base = settings.keycloak_base_url
    keycloak = {origin(base)}
    status, _, auth = request(
        base + "/realms/master/protocol/openid-connect/token",
        origins=keycloak,
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
    root = base + "/admin/realms/platform"
    email = "delivery-" + uuid.uuid4().hex + "@example.test"
    status, headers, _ = request(
        root + "/users",
        origins=keycloak,
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
    subject = user_id(headers["Location"])
    status, _, _ = request(
        root + "/users/" + subject, origins=keycloak, method="PUT", token=token, data={"lastName": "After"}
    )
    assert status == 204, f"User update returned {status}"
    query = urllib.parse.urlencode({"resourcePath": "users/" + subject, "operationTypes": "UPDATE"})
    deadline = time.monotonic() + 60
    event_id = None
    with sqlite3.connect("file:" + os.environ["IDENTITY_SYNC_DB"] + "?mode=ro", uri=True) as database:
        while time.monotonic() < deadline:
            status, _, events = request(root + "/admin-events?" + query, origins=keycloak, token=token)
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
                RECEIVER + "/v1/events",
                origins={RECEIVER},
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
