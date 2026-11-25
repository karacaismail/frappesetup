"""Magic link as a step inside the browser flow (owner decision, second review follow-up).

Conditions under test:
1. The link is a flow step. After the click the flow continues and the second factor is not skipped.
2. The link is bound to the login request and the browser session. Another browser cannot log in with it.
3. Short life (at most 300 s), single use, and a mail preview must not consume the link (mobile MT-7).
4. No REST endpoint issues links. The extension's REST resource is disabled and answers 404.
5. G-162: the answer does not show whether the account exists. Text, format and time are the same.
6. G-162: an expired link and a used link are refused.
7. G-162: the link code is not written to logs or events.
8. G-162: the system limits how often a link is sent to one address.
Expected values come from docs/sozlesmeler.md section 2, docs/kararlar/0003-keycloak-eklentileri.md and MT-7.
"""

from __future__ import annotations

import os
import re
import statistics
import subprocess
import time
import unittest
import urllib.parse
import uuid

from test_extensions import AKIS, _open, _cookie_opener, _form_action, _follow_keycloak_redirect
from test_second_factor import TOTP_USER, fresh_totp_code
from test_event_listener import _sink_requests
from helpers import DIRECTORY, admin, live_available, request, get_environment_value, read_realm, tenant_authorize_url, admin_token

MAGIC_LINK = "magiclink"
MAGIC_LINK_CONTINUATION = "magiclink-continuation"
MAGIC_LINK_REST_PATH = "magiclink-login"
MAGIC_LINK_CONFIG = "atonota-magic-link"
MAX_LIFETIME = 300
PINNED_COMMIT = "7b4ee949a39a7ee953987162479ae1da2c57c3cb"
PLAIN_USER = "ayse.ornek@example.test"
OTHER_USER = "mehmet.ornek@example.test"
UNKNOWN_USER = "kimse.yok@example.test"
# The send limit test makes a new address on every run. Slots stay taken for 15 minutes, so a fixed
# address would get no mail when the suite runs again within that time.
RATE_USER_PREFIX = "siklik-"
# Product owner decision (AJA-353): at most 3 mails to one address in 15 minutes.
SEND_LIMIT = 3
SEND_WINDOW_SECONDS = 900
SEND_LIMIT_KEY = "magiclink.send.limit"
SEND_WINDOW_KEY = "magiclink.send.window.seconds"
# Other live tests ask for more than 3 links to one address. The class raises the limit while it runs.
RAISED_SEND_LIMIT = 1000
FORK_DIRECTORY = "magic-link-fork"
SEND_ATTEMPTS = 8
# Median gap allowed between an existing and an unknown address. Measured gap on 24 November 2026: about 4 ms.
TIMING_TOLERANCE_SECONDS = 0.002
TIMING_ROUNDS = 15
EXPIRED_LIFETIME = 2


class MagicLinkFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.realm = read_realm()
        cls.dockerfile = (DIRECTORY / "Dockerfile").read_text(encoding="utf-8")
        cls.compose = (DIRECTORY.parents[1] / "dev" / "compose.keycloak.yaml").read_text(encoding="utf-8")
        cls.flows = {f["alias"]: f for f in cls.realm["authenticationFlows"]}
        cls.executions = [e for f in cls.realm["authenticationFlows"] for e in f["authenticationExecutions"]]

    def test_extension_is_built_from_pinned_source_with_checksum(self):
        # License Apache-2.0 verified in the repository LICENSE file; the source archive is pinned by commit and SHA-256.
        self.assertIn(f"ARG MAGICLINK_COMMIT={PINNED_COMMIT}", self.dockerfile)
        self.assertIn("cloudflightio/keycloak-magic-link/archive/${MAGICLINK_COMMIT}.tar.gz", self.dockerfile)
        self.assertRegex(self.dockerfile, r"--checksum=sha256:[0-9a-f]{64} \\\n\s+https://github.com/cloudflightio/keycloak-magic-link/archive")
        self.assertIn("-Dkeycloak.version=${KEYCLOAK_VERSION}", self.dockerfile)
        self.assertIn("ARG KEYCLOAK_VERSION=26.8.2", self.dockerfile)

    def test_magic_link_is_a_flow_step_followed_by_second_factor(self):
        steps = [e for e in self.executions if e.get("authenticator") == MAGIC_LINK]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["requirement"], "REQUIRED")
        self.assertEqual(steps[0]["authenticatorConfig"], MAGIC_LINK_CONFIG)
        parent = [f for f in self.realm["authenticationFlows"] if steps[0] in f["authenticationExecutions"]][0]
        after = [e for e in parent["authenticationExecutions"] if e["priority"] > steps[0]["priority"]]
        self.assertTrue(after and after[0]["authenticatorFlow"] and after[0]["requirement"] == "CONDITIONAL")
        second = self.flows[after[0]["flowAlias"]]["authenticationExecutions"]
        self.assertIn("conditional-user-configured", [e.get("authenticator") for e in second])
        self.assertIn("auth-otp-form", [e.get("authenticator") for e in second])
        self.assertNotIn(MAGIC_LINK_CONTINUATION, [e.get("authenticator") for e in self.executions])

    def test_magic_link_lifetime_is_short(self):
        config = {c["alias"]: c["config"] for c in self.realm["authenticatorConfig"]}[MAGIC_LINK_CONFIG]
        self.assertLessEqual(int(config["magickey.validity.duration"]), MAX_LIFETIME)

    def test_send_limit_is_three_mails_in_fifteen_minutes(self):
        config = {c["alias"]: c["config"] for c in self.realm["authenticatorConfig"]}[MAGIC_LINK_CONFIG]
        self.assertEqual(config[SEND_LIMIT_KEY], str(SEND_LIMIT))
        self.assertEqual(config[SEND_WINDOW_KEY], str(SEND_WINDOW_SECONDS))

    def test_image_builds_the_fork_files_over_the_pinned_source(self):
        # G-162: the changed files are copied over the unpacked pinned archive, then Maven builds.
        stage = self.dockerfile.split("AS magiclink-build", 1)[1].split("\nFROM ", 1)[0]
        copy = f"COPY {FORK_DIRECTORY}/src/ /build/keycloak-magic-link/src/"
        self.assertIn(copy, stage)
        self.assertLess(stage.index("tar -xzf"), stage.index(copy))
        self.assertLess(stage.index(copy), stage.index("mvn "))
        ignore = (DIRECTORY / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(f"!{FORK_DIRECTORY}/", ignore)
        self.assertIn(f"!{FORK_DIRECTORY}/**", ignore)
        fork = DIRECTORY / FORK_DIRECTORY
        self.assertTrue((fork / "NOTICE").is_file(), "Apache-2.0 section 4 asks for a change notice")
        for changed in sorted(fork.joinpath("src").rglob("*.java")):
            with self.subTest(file=changed.name):
                self.assertIn(changed.name, (fork / "NOTICE").read_text(encoding="utf-8"))

    def test_rest_resource_and_continuation_are_disabled_by_the_image(self):
        # Merge review E1: the setting lives in the image's conf/keycloak.conf (test_production_image).
        conf = (DIRECTORY / "conf" / "keycloak.conf").read_text(encoding="utf-8")
        self.assertIn("spi-realm-restapi-extension--magiclink-login--enabled=false", conf)
        self.assertIn("spi-authenticator--magiclink-continuation--enabled=false", conf)


def _magic_link_execution_id(admin_token: str) -> str:
    executions = admin(f"/authentication/flows/{AKIS}/executions", admin_token).json()
    return [e["id"] for e in executions if e.get("providerId") == MAGIC_LINK][0]


def _magic_link_config(token: str) -> tuple[str, dict]:
    """Returns the id and body of the live magic link step configuration."""
    executions = admin(f"/authentication/flows/{AKIS}/executions", token).json()
    config_id = [e for e in executions if e.get("providerId") == MAGIC_LINK][0]["authenticationConfig"]
    return config_id, admin(f"/authentication/config/{config_id}", token).json()


def _put_magic_link_config(config_id: str, body: dict, **values: str) -> int:
    changed = dict(body, config=dict(body["config"], **values))
    return admin(f"/authentication/config/{config_id}", admin_token(), "PUT", changed).status


class Mailpit:
    def __init__(self, base: str):
        self.base = base

    def clear(self):
        request("DELETE", f"{self.base}/api/v1/messages")

    def latest_link(self, recipient: str, wait_seconds: int = 20) -> str:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            for message in request("GET", f"{self.base}/api/v1/messages").json().get("messages", []):
                if any(a.get("Address") == recipient for a in message.get("To", [])):
                    detail = request("GET", f"{self.base}/api/v1/message/{message['ID']}").json()
                    text = (detail.get("Text") or "") + " " + (detail.get("HTML") or "")
                    found = re.search(r"https?://[^\s\"'<>]+login-actions/authenticate[^\s\"'<>]+magickey=[^\s\"'<>]+", text)
                    if found:
                        return found.group(0).replace("&amp;", "&")
            time.sleep(1)
        raise AssertionError(f"no magic link mail for {recipient}")


@unittest.skipUnless(live_available(), "KC_PUBLIC_URL missing, live Keycloak test skipped")
class MagicLinkLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kc = get_environment_value("KC_PUBLIC_URL")
        cls.admin_token = admin_token()
        cls.mailpit = Mailpit(f"http://127.0.0.1:{get_environment_value('MAILPIT_UI_PORT')}")
        cls.execution_id = _magic_link_execution_id(cls.admin_token)
        # Several tests ask for more than SEND_LIMIT links to one address. The limit test sets it back.
        cls.config_id, cls.file_config = _magic_link_config(cls.admin_token)
        status = _put_magic_link_config(cls.config_id, cls.file_config, **{SEND_LIMIT_KEY: str(RAISED_SEND_LIMIT)})
        if status != 204:
            raise AssertionError(f"raising the send limit failed: HTTP {status}")
        cls.addClassCleanup(lambda: admin(f"/authentication/config/{cls.config_id}", admin_token(), "PUT", cls.file_config))

    def _open_email_form(self):
        """Opens the login page and switches to the magic link step. Returns (opener, html)."""
        opener = _cookie_opener()
        status, _, html = _open(opener, tenant_authorize_url())
        self.assertEqual(status, 200)
        self.assertTrue("tryAnotherWay" in html, "login page must offer another way")
        status, _, html = _open(opener, _form_action(html), urllib.parse.urlencode({"tryAnotherWay": "on"}).encode())
        status, _, html = _open(opener, _form_action(html), urllib.parse.urlencode({"authenticationExecution": self.execution_id}).encode())
        self.assertEqual(status, 200)
        self.assertTrue('name="username"' in html and 'name="password"' not in html, "e-mail form expected")
        return opener, html

    def _submit_email(self, email: str):
        """Submits the address on a fresh e-mail form. Returns (opener, status, html, seconds)."""
        opener, html = self._open_email_form()
        started = time.perf_counter()
        status, _, html = _open(opener, _form_action(html), urllib.parse.urlencode({"username": email}).encode())
        return opener, status, html, time.perf_counter() - started

    def _request_link(self, email: str):
        """Opens the login page, switches to the magic link step and submits the e-mail address."""
        self.mailpit.clear()
        opener, status, _, _ = self._submit_email(email)
        self.assertEqual(status, 200)
        return opener, self.mailpit.latest_link(email)

    def _new_user(self, email: str) -> str:
        """Creates a user without a password for one test and deletes it afterwards."""
        body = {"username": email, "email": email, "emailVerified": True, "enabled": True,
                "firstName": "Sıklık", "lastName": "Örnek"}
        self.assertEqual(admin("/users", admin_token(), "POST", body).status, 201)
        user_id = admin(f"/users?email={urllib.parse.quote(email)}&exact=true", admin_token()).json()[0]["id"]
        self.addCleanup(lambda: admin(f"/users/{user_id}", admin_token(), "DELETE"))
        return email

    def _mail_count(self, recipient: str) -> int:
        messages = request("GET", f"{self.mailpit.base}/api/v1/messages").json().get("messages", [])
        return sum(1 for m in messages if any(a.get("Address") == recipient for a in m.get("To", [])))

    def test_link_logs_in_only_in_the_requesting_browser_and_only_once(self):
        opener, link = self._request_link(PLAIN_USER)
        # MT-7: a preview or scanner without the browser session must not consume the link.
        stranger = _cookie_opener()
        status, headers, _ = _follow_keycloak_redirect(stranger, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
        # The requesting browser still completes the login.
        status, headers, _ = _follow_keycloak_redirect(opener, link, self.kc)
        location = headers.get("Location", "")
        self.assertEqual(status, 302, "first click in the requesting browser must finish the login")
        self.assertTrue(location.startswith(get_environment_value("ATONOTA_SITE_TENANT1_URL")), f"HTTP {status}")
        self.assertTrue("code=" in location, f"HTTP {status}")
        # Single use: the same link does not work twice.
        status, headers, _ = _follow_keycloak_redirect(opener, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")

    def test_link_does_not_skip_totp(self):
        opener, link = self._request_link(TOTP_USER)
        status, headers, html = _follow_keycloak_redirect(opener, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
        self.assertTrue('name="otp"' in html, "the OTP form must follow the magic link")
        time.sleep(1.2)
        status, headers, html = _open(opener, _form_action(html), urllib.parse.urlencode({"otp": "000000"}).encode())
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
        self.assertTrue('name="otp"' in html, "wrong code must keep the OTP form")
        time.sleep(1.2)
        status, headers, _ = _open(opener, _form_action(html), urllib.parse.urlencode({"otp": fresh_totp_code()}).encode())
        self.assertEqual(status, 302)
        self.assertTrue("code=" in headers.get("Location", ""), f"HTTP {status}")

    def test_link_lifetime_matches_configuration(self):
        executions = admin(f"/authentication/flows/{AKIS}/executions", self.admin_token).json()
        step = [e for e in executions if e.get("providerId") == MAGIC_LINK][0]
        config = admin(f"/authentication/config/{step['authenticationConfig']}", self.admin_token).json()
        self.assertLessEqual(int(config["config"]["magickey.validity.duration"]), MAX_LIFETIME)

    def test_rest_resource_answers_404(self):
        # Condition 4: the extension's REST resource is disabled by SPI configuration.
        sample = "00000000-0000-4000-8000-000000000000"
        response = request("GET", f"{self.kc}/realms/platform/{MAGIC_LINK_REST_PATH}?id={sample}&magicKey={sample}")
        self.assertEqual(response.status, 404)

    def test_continuation_authenticator_is_not_available(self):
        providers = request("GET", f"{self.kc}/admin/serverinfo", token=self.admin_token).json()["providers"]
        self.assertIn(MAGIC_LINK, providers["authenticator"]["providers"])
        self.assertNotIn(MAGIC_LINK_CONTINUATION, providers["authenticator"]["providers"])

    def test_other_user_cannot_use_a_link_meant_for_someone_else(self):
        # The link is bound to the login request; the browser that started it is the only consumer.
        opener, link = self._request_link(OTHER_USER)
        other = _cookie_opener()
        _open(other, tenant_authorize_url())
        status, headers, _ = _follow_keycloak_redirect(other, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")

    # G-162 tests start here.

    def test_existing_and_unknown_address_get_the_same_text_and_format(self):
        _, known_status, known_html, _ = self._submit_email(PLAIN_USER)
        _, unknown_status, unknown_html, _ = self._submit_email(UNKNOWN_USER)
        self.assertEqual((known_status, unknown_status), (200, 200))
        self.assertEqual(_without_session_values(known_html), _without_session_values(unknown_html))
        self.assertNotIn(PLAIN_USER, known_html)
        self.assertNotIn(UNKNOWN_USER, unknown_html)

    def test_existing_and_unknown_address_take_the_same_time(self):
        # The extension sends the mail before it answers, and only for an existing user (AbstractMagicLinkAuthenticator).
        # Real SMTP makes the gap larger than the local Mailpit does.
        known, unknown = [], []
        for _ in range(TIMING_ROUNDS):
            known.append(self._submit_email(PLAIN_USER)[3])
            unknown.append(self._submit_email(UNKNOWN_USER)[3])
        gap = statistics.median(known) - statistics.median(unknown)
        self.assertLessEqual(abs(gap), TIMING_TOLERANCE_SECONDS,
                             f"median gap {gap * 1000:.1f} ms shows whether the account exists")

    def test_unknown_address_gets_no_mail(self):
        self.mailpit.clear()
        self._submit_email(UNKNOWN_USER)
        time.sleep(2)
        self.assertEqual(self._mail_count(UNKNOWN_USER), 0)

    def test_send_rate_is_limited_per_address(self):
        # The realm file value applies here. Other tests in this class run with the raised limit.
        self.assertEqual(self.file_config["config"][SEND_LIMIT_KEY], str(SEND_LIMIT))
        _, raised = _magic_link_config(admin_token())
        self.assertEqual(_put_magic_link_config(self.config_id, raised, **{SEND_LIMIT_KEY: str(SEND_LIMIT)}), 204)
        self.addCleanup(lambda: admin(f"/authentication/config/{self.config_id}", admin_token(), "PUT", raised))
        rate_user = self._new_user(f"{RATE_USER_PREFIX}{uuid.uuid4().hex[:12]}@example.test")
        self.mailpit.clear()
        answers = set()
        for _ in range(SEND_ATTEMPTS):
            _, status, html, _ = self._submit_email(rate_user)
            self.assertNotIn(rate_user, html)
            answers.add((status, _without_session_values(html)))
        time.sleep(3)
        sent = self._mail_count(rate_user)
        self.assertEqual(sent, SEND_LIMIT, f"{sent} mails for {SEND_ATTEMPTS} requests, expected exactly {SEND_LIMIT}")
        # Over the limit the person sees the same answer as before.
        self.assertEqual(len(answers), 1, "the answer changed after the send limit")
        self.assertEqual(next(iter(answers))[0], 200)

    def test_expired_link_is_refused(self):
        config_id, original = _magic_link_config(self.admin_token)
        short = dict(original, config=dict(original["config"], **{"magickey.validity.duration": str(EXPIRED_LIFETIME)}))
        self.assertEqual(admin(f"/authentication/config/{config_id}", self.admin_token, "PUT", short).status, 204)
        self.addCleanup(lambda: admin(f"/authentication/config/{config_id}", admin_token(), "PUT", original))
        opener, link = self._request_link(PLAIN_USER)
        time.sleep(EXPIRED_LIFETIME + 2)
        status, headers, html = _follow_keycloak_redirect(opener, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")
        self.assertTrue('name="username"' in html, "an expired link must return to the e-mail form")

    def test_used_link_is_refused_in_the_same_browser(self):
        opener, link = self._request_link(PLAIN_USER)
        status, headers, _ = _follow_keycloak_redirect(opener, link, self.kc)
        self.assertTrue("code=" in headers.get("Location", ""), f"HTTP {status}")
        status, headers, _ = _follow_keycloak_redirect(opener, link, self.kc)
        self.assertFalse("code=" in headers.get("Location", ""), f"HTTP {status}")

    def test_link_code_is_not_in_logs_or_events(self):
        since = int(time.time()) - 1
        opener, link = self._request_link(PLAIN_USER)
        magic_key = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)["magickey"][0]
        self.assertGreaterEqual(len(magic_key), 16)
        _follow_keycloak_redirect(opener, link, self.kc)
        _follow_keycloak_redirect(opener, link, self.kc)
        time.sleep(2)
        # Same container naming as _sink_requests in test_event_listener.
        context = os.environ.get("DOCKER_CONTEXT", "colima-factory")
        project = os.environ.get("COMPOSE_PROJECT_NAME", "fs-kimlik-realm")
        logs = subprocess.run(["docker", "--context", context, "logs", "--since", str(since), f"{project}-keycloak-1"],
                              capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(logs.returncode, 0, "Keycloak logs are not readable")
        self.assertNotIn(magic_key, logs.stdout + logs.stderr, "the link code is in the Keycloak log")
        events = admin("/events?max=200", self.admin_token)
        self.assertEqual(events.status, 200)
        self.assertNotIn(magic_key, events.body.decode("utf-8", "replace"), "the link code is in the login events")
        self.assertNotIn(magic_key, repr(_sink_requests()), "the link code is in the event webhook")


def _without_session_values(html: str) -> str:
    """Removes values that change on every login request, so two answers can be compared."""
    html = re.sub(r"(session_code|execution|tab_id|client_data|kc_locale)=[^&\"]*", r"\1=", html)
    return re.sub(r'checkAuthSession\(\s*"[^"]*"', 'checkAuthSession("")', html)
