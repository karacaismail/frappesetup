"""Tests for the Jenkins side: bin/ scripts with a fake ssh and scp, and rules of the Jenkinsfiles.

The fake ssh writes its arguments to a log and runs nothing. These tests need only bash, so they
also run on macOS. Design: backend/docs/dagitim/ortamlar.md.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
JENKINS = DEPLOY / "jenkins"
sys.path.insert(0, str(DEPLOY))

import release  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "a" * 64

FAKE = r"""#!/usr/bin/env bash
{ printf '%s' "$(basename "$0")"; printf '\t%s' "$@"; printf '\n'; } >>"$FAKE_LOG"
exit 0
"""


def manifest(**overrides):
    components = {
        name: {"image": f"ghcr.io/karacaismail/atonota-{name}@{DIGEST}"}
        for name in ("tenant", "keycloak", "identity-sync")
    }
    data = release.new_manifest("backend", COMMIT, 7, components)
    data.update(overrides)
    return data


class DeployScript(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        fake_bin = self.folder / "bin"
        fake_bin.mkdir()
        for name in ("ssh", "scp"):
            (fake_bin / name).write_text(FAKE)
            (fake_bin / name).chmod(0o755)
        self.log = self.folder / "calls.log"
        self.environment = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "FAKE_LOG": str(self.log)}
        self.release = self.folder / "release"
        self.release.mkdir()

    def deploy(self, data, env="alpha"):
        (self.release / "release.json").write_text(json.dumps(data))
        return subprocess.run(
            [str(DEPLOY / "bin" / "deploy"), env, str(self.release)],
            env=self.environment,
            capture_output=True,
            text=True,
        )

    def calls(self):
        if not self.log.exists():
            return []
        return [line.split("\t") for line in self.log.read_text().splitlines()]

    def test_remote_commands_reach_the_server_as_the_same_words(self):
        result = self.deploy(manifest())
        self.assertEqual(result.returncode, 0, result.stderr)
        incoming = f"/srv/atonota/alpha/incoming/backend-{COMMIT[:12]}-b7"
        commands = [call for call in self.calls() if call[0] == "ssh"]
        self.assertEqual(len(commands), 2, commands)
        for call in commands:
            self.assertEqual(call[-3:-1], ["--", "deploy-alpha@atonota-nonprod"])
            # ssh joins its arguments and the server shell splits them again. The last argument
            # must already be quoted, so the server sees exactly these words.
        self.assertEqual(shlex.split(commands[0][-1]), ["install", "-d", "-m", "0750", incoming])
        self.assertEqual(shlex.split(commands[1][-1]), [f"{incoming}/apply", "alpha", incoming])
        copies = [call for call in self.calls() if call[0] == "scp"]
        self.assertEqual(copies[0][-1], f"deploy-alpha@atonota-nonprod:{incoming}/")

    def test_each_environment_uses_its_own_server_user(self):
        data = manifest()
        result = self.deploy(data, "beta")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all("deploy-beta@atonota-nonprod" in " ".join(call) for call in self.calls()))

    def test_a_bad_build_field_stops_before_any_connection(self):
        build = "1;touch${IFS}/tmp/pwned"
        data = manifest(build=build, release_id=release.release_id("backend", COMMIT, build))
        result = self.deploy(data, "beta")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])


def jenkinsfile(name):
    text = (JENKINS / name).read_text()
    # Drop line comments, so the rules below test code only.
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class Jenkinsfiles(unittest.TestCase):
    AUTOMATIC = ("backend.Jenkinsfile", "web.Jenkinsfile")
    ALL = AUTOMATIC + ("promote.Jenkinsfile",)

    def test_every_ssh_key_belongs_to_one_environment(self):
        # One shared key once opened every server (review 1, finding 6).
        for name in self.ALL:
            text = jenkinsfile(name)
            self.assertNotIn("'atonota-deploy-ssh'", text, name)
            for credential in re.findall(r"sshagent\(credentials: \[([^\]]*)\]", text):
                self.assertRegex(credential, r'^"atonota-deploy-ssh-\$\{[a-zA-Z.]+\}"$', name)

    def test_automatic_jobs_never_reach_rc_or_prod(self):
        # The jobs that main starts live in a Jenkins folder without the rc and prod keys.
        for name in self.AUTOMATIC:
            text = jenkinsfile(name)
            self.assertNotRegex(text, r"promote\('(rc|prod)'", name)
            self.assertNotIn("atonota-deploy-ssh-rc", text, name)
            self.assertNotIn("atonota-deploy-ssh-prod", text, name)

    def test_later_stages_reuse_the_first_checkout(self):
        # A stage after an approval must not check out a newer main (review 1, finding 7).
        for name in self.ALL:
            text = jenkinsfile(name)
            self.assertIn("skipDefaultCheckout()", text, name)
            self.assertEqual(text.count("checkout scm"), 1, name)
            self.assertIn("stash name: 'deploy'", text, name)
            self.assertIn("unstash 'deploy'", text, name)

    def test_automatic_rollback_names_the_failed_release(self):
        # Only the release that failed may be undone (review 1, finding E1).
        for name in self.ALL:
            text = jenkinsfile(name)
            for line in re.findall(r".*bin/rollback.*", text):
                if "ACTION" in line:
                    continue
                self.assertIn("--failed", line, f"{name}: {line.strip()}")

    def test_approval_does_not_hold_an_agent(self):
        # An input step inside steps keeps the agent busy until someone answers (finding K4).
        for name in self.ALL:
            self.assertNotRegex(jenkinsfile(name), r"\binput\(", name)

    def test_promotion_compares_with_the_jenkins_archive_and_checks_again_after_approval(self):
        text = jenkinsfile("promote.Jenkinsfile")
        self.assertIn("copyArtifacts(", text)
        self.assertIn("same-release", text)
        self.assertIn("promote-check", text)
        # The same source check runs before the approval and again after it (finding K5).
        approval = text.index("stage('Approve promotion')")
        self.assertIn("checkSource(", text[:approval])
        self.assertIn("checkSource(", text[approval:])
        for name in self.AUTOMATIC:
            self.assertIn("copyArtifactPermission(", jenkinsfile(name), name)


class EdgeHeaders(unittest.TestCase):
    def test_every_host_refuses_framing_by_other_sites(self):
        # Static panel files and Keycloak got only three headers from the edge (finding K3).
        caddyfile = (DEPLOY / "compose" / "Caddyfile").read_text()
        block = caddyfile[caddyfile.index("(security_headers)"):caddyfile.index("import /etc/caddy/sites")]
        self.assertIn("?X-Frame-Options SAMEORIGIN", block)
        self.assertIn("?Content-Security-Policy \"frame-ancestors 'self'\"", block)
        template = (DEPLOY / "compose" / "site.caddy.template").read_text()
        hosts = [line for line in template.splitlines() if line.endswith("{") and line.startswith("__")]
        self.assertEqual(template.count("import security_headers"), len(hosts))


if __name__ == "__main__":
    unittest.main()
