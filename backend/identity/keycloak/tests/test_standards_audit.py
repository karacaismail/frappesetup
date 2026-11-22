"""Standards self audit (docs/standartlar/frappe-python-disi-standartlari.md and
frappe-python-standartlari.md): one test per rule this job did not meet.

Each expected value comes from the rule text, not from the code under test.
"""

from __future__ import annotations

import os
import re
import unittest
from unittest import mock

from yardimci import KLASOR, ORNEK_ENV, realm_oku

DOCKERFILE = (KLASOR / "Dockerfile").read_text(encoding="utf-8")
POM = (KLASOR / "event-listener" / "pom.xml").read_text(encoding="utf-8")
SCRIPT = (KLASOR / "bin" / "kc-dev.sh").read_text(encoding="utf-8")
README = (KLASOR / "README.md").read_text(encoding="utf-8")
# The six Turkish letters outside ASCII, lower and upper case, as escapes so this file stays ASCII.
TURKISH_LETTERS = re.compile("[\u00e7\u011f\u0131\u00f6\u015f\u00fc\u00c7\u011e\u0130\u00d6\u015e\u00dc]")
# Files written in this branch after D-12 (22 November 2026, 08:36). Older files keep their names until
# the shared renaming job runs.
NEW_TEST_FILES = (
    "test_event_listener.py", "test_realm_backlog.py", "test_account_backlog.py", "test_session_lifetimes.py",
    "test_production_image.py", "test_dev_script_secrets.py", "test_synthetic_secrets.py",
    "test_standards_audit.py",
)


def _case_branch(name: str) -> str:
    match = re.search(rf"\n  {re.escape(name)}\)\n(.*?)\n    ;;\n", SCRIPT, re.S)
    if match is None:
        raise AssertionError(f"case branch {name} is missing")
    return match.group(1)


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


class SingleSourceTest(unittest.TestCase):
    """H-7: one setting lives in one place."""

    def test_keycloak_version_is_defined_once_in_the_dockerfile(self):
        self.assertEqual(len(re.findall(r"26\.8\.2", DOCKERFILE)), 1, "write the version once, in ARG")
        self.assertRegex(DOCKERFILE, r"(?m)^ARG KEYCLOAK_VERSION=26\.8\.2$")
        self.assertIn("quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}", DOCKERFILE)
        self.assertIn("-Dkeycloak.version=${KEYCLOAK_VERSION}", DOCKERFILE)

    def test_pom_default_matches_the_dockerfile(self):
        arg = re.search(r"(?m)^ARG KEYCLOAK_VERSION=(\S+)$", DOCKERFILE).group(1)
        self.assertEqual(re.search(r"<keycloak.version>([^<]+)</keycloak.version>", POM).group(1), arg)

    def test_maven_image_digest_is_defined_once(self):
        self.assertEqual(len(re.findall(r"sha256:99e61abc", DOCKERFILE)), 1)
        self.assertIn("FROM ${MAVEN_IMAGE} AS event-listener-build", DOCKERFILE)


class EnglishNamesTest(unittest.TestCase):
    """H-10, M-8 and F-4 (D-12): new names and new source text are English."""

    def test_new_realm_flow_names_are_english(self):
        realm = realm_oku()
        names = [f["alias"] for f in realm["authenticationFlows"]]
        names += [c["alias"] for c in realm["authenticatorConfig"]]
        names += [e.get("flowAlias", "") for f in realm["authenticationFlows"] for e in f["authenticationExecutions"]]
        for word in ("sihirli", "yontem", "duzey", "baglanti"):
            self.assertFalse([n for n in names if word in n], word)

    def test_realm_source_text_is_english(self):
        found = [s for s in _strings(realm_oku()) if TURKISH_LETTERS.search(s)]
        self.assertEqual(found, [])

    def test_new_script_names_are_english(self):
        for name in ("LIMA_VARSAYILAN", "ornek_satiri", "pid_dosyasi", "yonlendirme", "prod_etiket",
                     "prod_calistir", "prod_temizle", "prod_gunluk", "prod_tunel_pid", "kc_kimlik",
                     "realm-yenile", "realm-sil-yalniz"):
            self.assertNotIn(name, SCRIPT, name)

    def test_new_script_commands_print_english(self):
        for branch in ("prod-check", "realm-reload", "realm-delete-only"):
            self.assertIsNone(TURKISH_LETTERS.search(_case_branch(branch)), branch)

    def test_new_test_files_are_english(self):
        for name in NEW_TEST_FILES:
            text = (KLASOR / "tests" / name).read_text(encoding="utf-8")
            self.assertIsNone(TURKISH_LETTERS.search(text), name)
            self.assertNotRegex(text, r"\byok\b", name)


class DebtMarkerTest(unittest.TestCase):
    """L-2: technical debt is marked where it lives."""

    def test_magic_link_build_carries_a_debt_marker(self):
        stage = DOCKERFILE.split("AS magiclink-build", 1)[1].split("\nFROM ", 1)[0]
        before = DOCKERFILE.split("AS magiclink-build", 1)[0].rsplit("\n\n", 1)[-1]
        self.assertIn("BORC(mvp)", before + stage)


class PersonalDataTest(unittest.TestCase):
    """F-5 and G-15: no personal data in logs; stored events have a limit."""

    def test_admin_events_expire(self):
        realm = realm_oku()
        self.assertTrue(realm["adminEventsEnabled"])
        # Keycloak 26.8.2 keeps this limit as a realm attribute, not as a representation field
        # (model/jpa/.../RealmAttributes.java line 56); a top-level key stops the realm import.
        self.assertNotIn("adminEventsExpiration", realm)
        limit = int(realm["attributes"]["adminEventsExpiration"])
        self.assertGreater(limit, 0)
        self.assertLessEqual(limit, realm["eventsExpiration"])

    def test_events_are_not_written_to_the_container_log(self):
        # The jboss-logging listener writes every event, IP address and user name included, to the log.
        self.assertNotIn("jboss-logging", realm_oku()["eventsListeners"])


class ShellQuotingTest(unittest.TestCase):
    """Q-4: variables are quoted; a list of arguments is an array."""

    def test_no_unquoted_positional_or_pid_expansion(self):
        for line in SCRIPT.splitlines():
            if line.lstrip().startswith("#") or "awk " in line:
                continue  # comments, and awk programs whose $N are awk fields, not shell expansions
            # Drop double-quoted parts and single-quoted parts (awk programs), then look for a bare
            # positional, "$!" or "$@" expansion.
            bare = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
            bare = re.sub(r"'[^']*'", "''", bare)
            self.assertNotRegex(bare, r"\$[0-9!@*]", line)


class DocumentationTest(unittest.TestCase):
    """U-6: the guide follows the setup."""

    def test_every_command_is_documented(self):
        commands = re.findall(r"\n  ([a-z][a-z-]*)\)", SCRIPT)
        usage = SCRIPT.splitlines()[2]
        for command in commands:
            self.assertIn(command, usage, command)
            self.assertIn(f"kc-dev.sh {command}", README, command)

    def test_files_and_extensions_are_documented(self):
        for item in ("event-listener/", "event-sink/", "conf/", "production.env.example"):
            self.assertIn(item, README, item)
        for jar in re.findall(r"/opt/keycloak/providers/([\w.-]+?)(?:-[0-9a-f]{7}|-identity-sync|-[0-9.]+)?\.jar",
                              DOCKERFILE):
            self.assertIn(jar.split("-1.")[0], README, jar)

    def test_dockerignore_comment_names_every_folder(self):
        comment = (KLASOR / ".dockerignore").read_text(encoding="utf-8").splitlines()[0]
        for folder in ("realm", "themes", "conf", "event-listener", "event-sink"):
            self.assertIn(folder, comment, folder)

    def test_build_output_is_not_tracked(self):
        self.assertIn("event-listener/target/", (KLASOR / ".gitignore").read_text(encoding="utf-8"))


class SinkErrorTest(unittest.TestCase):
    """V-11: catch only what can be handled; do not return a made-up value in place of an error."""

    def test_unreachable_sink_raises(self):
        from test_event_listener import _sink_requests

        with mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "fs-kimlik-realm-missing-project"}):
            with self.assertRaises(RuntimeError):
                _sink_requests()


class EnvExampleTest(unittest.TestCase):
    def test_example_file_is_valid_for_docker_env_file(self):
        # docker --env-file does not strip trailing comments, so a value must not carry one.
        for line in ORNEK_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                self.assertNotIn(" #", line, line)


class ResponseCleanupTest(unittest.TestCase):
    def test_http_error_response_body_is_closed_after_reading(self):
        import io
        import urllib.error

        from yardimci import istek

        url = "https://example.test/"
        body = io.BytesIO(b"error")
        error = urllib.error.HTTPError(url, 404, "Not Found", {}, body)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            self.assertEqual(istek("GET", url).durum, 404)
        self.assertTrue(body.closed)


class NoRawResponseInMessagesTest(unittest.TestCase):
    """Third review: a failing live test must not write a response body to the log. A token endpoint
    that wrongly accepts a request returns tokens in that body."""

    def test_tests_never_slice_a_raw_body_into_a_message(self):
        for path in sorted((KLASOR / "tests").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            # A slice of a response object's raw body; a local dict of decoded claims is fine.
            self.assertIsNone(re.search(r"\.govde\[", text), path.name)

    def test_unexpected_redirect_reports_only_status(self):
        from yardimci import HttpYanit, assert_refused_without_pkce

        response = HttpYanit(302, b"", {"Location": "https://example.test/?code=dummy-code"})
        with self.assertRaisesRegex(AssertionError, r"^True is not false : HTTP 302$"):
            assert_refused_without_pkce(self, response)

    def test_unreadable_json_reports_only_status(self):
        from yardimci import HttpYanit

        with self.assertRaisesRegex(ValueError, r"^HTTP 502$"):
            HttpYanit(502, b"\xff", {}).json()

    def test_safe_detail_keeps_status_and_error_code_only(self):
        from yardimci import HttpYanit, safe_detail

        token_body = b'{"access_token":"eyJhbGciOiJSUzI1NiJ9.secret","error":"invalid_grant"}'
        detail = safe_detail(HttpYanit(400, token_body, {}))
        self.assertEqual(detail, "HTTP 400 invalid_grant")
        self.assertEqual(safe_detail(HttpYanit(200, b'{"access_token":"eyJ.x.y"}', {})), "HTTP 200")
        self.assertEqual(safe_detail(HttpYanit(502, b"<html>bad gateway</html>", {})), "HTTP 502")
        self.assertEqual(safe_detail(HttpYanit(400, b'{"error":"opaque_secret"}', {})), "HTTP 400")


if __name__ == "__main__":
    unittest.main()
